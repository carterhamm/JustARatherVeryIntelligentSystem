import Foundation
import HealthKit
import BackgroundTasks
import UIKit
import os.log

/// Actor-based HealthKit sync service using anchor-based incremental queries,
/// persistent outbox for offline resilience, and background delivery.
actor HealthSyncService {
    static let shared = HealthSyncService()

    // MARK: - Constants

    private static let bgTaskID = "dev.jarvis.malibupoint.healthsync"
    private static let outboxFile = "health_outbox.json"
    private static let anchorPrefix = "hk_anchor_"
    private static let debounceInterval: TimeInterval = 2.0
    private static let maxBatchSize = 500

    private let logger = Logger(subsystem: "dev.jarvis.malibupoint", category: "HealthSync")

    // MARK: - HealthKit Store

    nonisolated let store: HKHealthStore? = {
        guard HKHealthStore.isHealthDataAvailable() else { return nil }
        return HKHealthStore()
    }()

    // MARK: - Tracked Types

    private let quantityTypes: [(HKQuantityTypeIdentifier, String, String)] = [
        (.stepCount, "steps", "count"),
        (.heartRate, "heart_rate", "count/min"),
        (.restingHeartRate, "resting_heart_rate", "count/min"),
        (.activeEnergyBurned, "active_energy", "kcal"),
    ]

    private let categoryTypes: [(HKCategoryTypeIdentifier, String)] = [
        (.sleepAnalysis, "sleep_analysis"),
    ]

    // MARK: - State

    private var debounceTimers: [String: Task<Void, Never>] = [:]
    private(set) var isRunning = false
    private var deviceID: String = "unknown"

    // MARK: - Authorization

    func requestAuthorization() async -> Bool {
        guard let store else {
            logger.warning("HealthKit not available on this device")
            return false
        }

        var readTypes = Set<HKObjectType>()

        for (id, _, _) in quantityTypes {
            if let type = HKQuantityType.quantityType(forIdentifier: id) {
                readTypes.insert(type)
            }
        }

        for (id, _) in categoryTypes {
            if let type = HKCategoryType.categoryType(forIdentifier: id) {
                readTypes.insert(type)
            }
        }

        readTypes.insert(HKObjectType.workoutType())

        do {
            try await store.requestAuthorization(toShare: [], read: readTypes)
            logger.info("HealthKit authorization granted")
            return true
        } catch {
            logger.error("HealthKit authorization failed: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Background Delivery Setup

    func startBackgroundSync() async {
        guard !isRunning else { return }
        guard let store else { return }

        isRunning = true

        // Cache device ID from main actor
        self.deviceID = await MainActor.run {
            UIDevice.current.identifierForVendor?.uuidString ?? "unknown"
        }

        logger.info("Starting HealthKit background sync")

        // Enable background delivery for each type
        for (id, label, _) in quantityTypes {
            guard let type = HKQuantityType.quantityType(forIdentifier: id) else { continue }
            do {
                try await store.enableBackgroundDelivery(for: type, frequency: .immediate)
                setupObserver(for: type, label: label, store: store)
                logger.info("Background delivery enabled: \(label)")
            } catch {
                logger.error("Background delivery failed for \(label): \(error.localizedDescription)")
            }
        }

        for (id, label) in categoryTypes {
            guard let type = HKCategoryType.categoryType(forIdentifier: id) else { continue }
            do {
                try await store.enableBackgroundDelivery(for: type, frequency: .immediate)
                setupObserver(for: type, label: label, store: store)
                logger.info("Background delivery enabled: \(label)")
            } catch {
                logger.error("Background delivery failed for \(label): \(error.localizedDescription)")
            }
        }

        // Workouts
        let workoutType = HKObjectType.workoutType()
        do {
            try await store.enableBackgroundDelivery(for: workoutType, frequency: .immediate)
            setupObserver(for: workoutType, label: "workout", store: store)
            logger.info("Background delivery enabled: workout")
        } catch {
            logger.error("Background delivery failed for workout: \(error.localizedDescription)")
        }

        // Foreground catch-up: sync everything on launch
        await performFullSync()

        // Flush any outbox items from previous sessions
        await flushOutbox()
    }

    // MARK: - Observer Queries (Debounced)

    private nonisolated func setupObserver(for type: HKObjectType, label: String, store: HKHealthStore) {
        guard let sampleType = type as? HKSampleType else { return }

        let query = HKObserverQuery(sampleType: sampleType, predicate: nil) { _, completionHandler, error in
            guard error == nil else {
                completionHandler()
                return
            }

            Task {
                await self.debouncedSync(label: label, type: type)
                completionHandler()
            }
        }

        store.execute(query)
    }

    private func debouncedSync(label: String, type: HKObjectType) {
        debounceTimers[label]?.cancel()

        debounceTimers[label] = Task {
            try? await Task.sleep(nanoseconds: UInt64(Self.debounceInterval * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await syncType(type, label: label)
        }
    }

    // MARK: - Anchor-Based Incremental Sync

    private func performFullSync() async {
        logger.info("Performing full foreground catch-up sync")

        for (id, label, _) in quantityTypes {
            guard let type = HKQuantityType.quantityType(forIdentifier: id) else { continue }
            await syncType(type, label: label)
        }

        for (id, label) in categoryTypes {
            guard let type = HKCategoryType.categoryType(forIdentifier: id) else { continue }
            await syncType(type, label: label)
        }

        await syncType(HKObjectType.workoutType(), label: "workout")
    }

    private func syncType(_ type: HKObjectType, label: String) async {
        guard let store, let sampleType = type as? HKSampleType else { return }

        let anchor = loadAnchor(for: label)

        do {
            let (samples, newAnchor) = try await queryNewSamples(
                store: store, type: sampleType, anchor: anchor
            )

            guard !samples.isEmpty else {
                logger.debug("No new samples for \(label)")
                return
            }

            logger.info("Found \(samples.count) new \(label) samples")

            let healthSamples = convertToHealthSamples(samples, label: label)

            // Batch into chunks
            let chunks = stride(from: 0, to: healthSamples.count, by: Self.maxBatchSize).map {
                Array(healthSamples[$0..<min($0 + Self.maxBatchSize, healthSamples.count)])
            }

            var allUploaded = true
            for chunk in chunks {
                let success = await uploadSamples(chunk)
                if !success {
                    allUploaded = false
                    await saveToOutbox(chunk)
                }
            }

            // Only persist anchor if all uploads succeeded (or went to outbox)
            if let newAnchor {
                saveAnchor(newAnchor, for: label)
            }

            if allUploaded {
                logger.info("Synced \(samples.count) \(label) samples to backend")
            }
        } catch {
            logger.error("Sync failed for \(label): \(error.localizedDescription)")
        }
    }

    private func queryNewSamples(
        store: HKHealthStore,
        type: HKSampleType,
        anchor: HKQueryAnchor?
    ) async throws -> ([HKSample], HKQueryAnchor?) {
        try await withCheckedThrowingContinuation { continuation in
            let query = HKAnchoredObjectQuery(
                type: type,
                predicate: nil,
                anchor: anchor,
                limit: HKObjectQueryNoLimit
            ) { _, added, _, newAnchor, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: (added ?? [], newAnchor))
            }

            store.execute(query)
        }
    }

    // MARK: - Sample Conversion

    private func convertToHealthSamples(_ samples: [HKSample], label: String) -> [HealthSample] {
        samples.compactMap { sample in
            if let quantitySample = sample as? HKQuantitySample {
                return convertQuantitySample(quantitySample, label: label)
            } else if let categorySample = sample as? HKCategorySample {
                return convertCategorySample(categorySample, label: label)
            } else if let workout = sample as? HKWorkout {
                return convertWorkout(workout)
            }
            return nil
        }
    }

    private func convertQuantitySample(_ sample: HKQuantitySample, label: String) -> HealthSample? {
        let unitInfo = quantityTypes.first { $0.1 == label }
        guard let unitString = unitInfo?.2 else { return nil }

        let unit: HKUnit
        switch unitString {
        case "count": unit = .count()
        case "count/min": unit = HKUnit.count().unitDivided(by: .minute())
        case "kcal": unit = .kilocalorie()
        default: return nil
        }

        return HealthSample(
            sampleType: label,
            value: sample.quantity.doubleValue(for: unit),
            unit: unitString,
            startDate: sample.startDate,
            endDate: sample.endDate,
            sourceName: sample.sourceRevision.source.name
        )
    }

    private func convertCategorySample(_ sample: HKCategorySample, label: String) -> HealthSample {
        let sleepValue: String
        if label == "sleep_analysis" {
            switch sample.value {
            case HKCategoryValueSleepAnalysis.inBed.rawValue: sleepValue = "in_bed"
            case HKCategoryValueSleepAnalysis.asleepCore.rawValue: sleepValue = "asleep_core"
            case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: sleepValue = "asleep_deep"
            case HKCategoryValueSleepAnalysis.asleepREM.rawValue: sleepValue = "asleep_rem"
            case HKCategoryValueSleepAnalysis.awake.rawValue: sleepValue = "awake"
            default: sleepValue = "unknown"
            }
        } else {
            sleepValue = "\(sample.value)"
        }

        return HealthSample(
            sampleType: label,
            value: Double(sample.value),
            unit: sleepValue,
            startDate: sample.startDate,
            endDate: sample.endDate,
            sourceName: sample.sourceRevision.source.name
        )
    }

    private func convertWorkout(_ workout: HKWorkout) -> HealthSample {
        HealthSample(
            sampleType: "workout",
            value: workout.duration,
            unit: "seconds",
            startDate: workout.startDate,
            endDate: workout.endDate,
            sourceName: workout.sourceRevision.source.name,
            metadata: [
                "activity_type": "\(workout.workoutActivityType.rawValue)",
                "total_energy": workout.totalEnergyBurned.map {
                    "\($0.doubleValue(for: .kilocalorie()))"
                } ?? "0",
                "total_distance": workout.totalDistance.map {
                    "\($0.doubleValue(for: .meter()))"
                } ?? "0",
            ]
        )
    }

    // MARK: - Network Upload

    private func uploadSamples(_ samples: [HealthSample]) async -> Bool {
        let request = HealthSyncRequest(samples: samples)

        do {
            let _: HealthSyncResponse = try await APIClient.shared.request(
                JARVISConfig.HealthSync.sync,
                method: "POST",
                body: request,
                authenticated: true
            )
            return true
        } catch {
            logger.error("Upload failed: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Persistent Outbox

    private var outboxURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(Self.outboxFile)
    }

    private func saveToOutbox(_ samples: [HealthSample]) async {
        var existing = loadOutbox()
        existing.append(contentsOf: samples)

        // Cap outbox at 5000 samples — drop oldest if exceeded
        if existing.count > 5000 {
            existing = Array(existing.suffix(5000))
        }

        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(existing)
            try data.write(to: outboxURL, options: .atomic)
            logger.info("Saved \(samples.count) samples to outbox (total: \(existing.count))")
        } catch {
            logger.error("Failed to save outbox: \(error.localizedDescription)")
        }
    }

    private func loadOutbox() -> [HealthSample] {
        guard FileManager.default.fileExists(atPath: outboxURL.path) else { return [] }

        do {
            let data = try Data(contentsOf: outboxURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            return try decoder.decode([HealthSample].self, from: data)
        } catch {
            logger.error("Failed to load outbox: \(error.localizedDescription)")
            return []
        }
    }

    private func clearOutbox() {
        try? FileManager.default.removeItem(at: outboxURL)
    }

    func flushOutbox() async {
        let pending = loadOutbox()
        guard !pending.isEmpty else { return }

        logger.info("Flushing \(pending.count) outbox samples")

        let chunks = stride(from: 0, to: pending.count, by: Self.maxBatchSize).map {
            Array(pending[$0..<min($0 + Self.maxBatchSize, pending.count)])
        }

        var failedSamples: [HealthSample] = []
        for chunk in chunks {
            let success = await uploadSamples(chunk)
            if !success {
                failedSamples.append(contentsOf: chunk)
            }
        }

        if failedSamples.isEmpty {
            clearOutbox()
            logger.info("Outbox flushed successfully")
        } else {
            // Rewrite outbox with only failed items
            clearOutbox()
            await saveToOutbox(failedSamples)
            logger.warning("\(failedSamples.count) samples remain in outbox after flush")
        }
    }

    // MARK: - Anchor Persistence (UserDefaults)

    private func loadAnchor(for label: String) -> HKQueryAnchor? {
        let key = Self.anchorPrefix + label
        guard let data = UserDefaults.standard.data(forKey: key) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    private func saveAnchor(_ anchor: HKQueryAnchor, for label: String) {
        let key = Self.anchorPrefix + label
        if let data = try? NSKeyedArchiver.archivedData(
            withRootObject: anchor, requiringSecureCoding: true
        ) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    // MARK: - BGAppRefreshTask (Safety Net)

    /// Register the background task identifier — call from app init, before scene setup.
    nonisolated static func registerBackgroundTask() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: bgTaskID,
            using: nil
        ) { task in
            guard let refreshTask = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            Task {
                await HealthSyncService.shared.handleBackgroundRefresh(refreshTask)
            }
        }
    }

    /// Schedule next background refresh — call whenever entering background.
    nonisolated static func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: bgTaskID)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            Logger(subsystem: "dev.jarvis.malibupoint", category: "HealthSync")
                .error("Failed to schedule BG refresh: \(error.localizedDescription)")
        }
    }

    private func handleBackgroundRefresh(_ task: BGAppRefreshTask) async {
        // Schedule next refresh before doing work
        Self.scheduleBackgroundRefresh()

        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }

        logger.info("Background refresh triggered")
        await performFullSync()
        await flushOutbox()
        task.setTaskCompleted(success: true)
    }
}
