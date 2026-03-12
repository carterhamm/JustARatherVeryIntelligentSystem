import Foundation
import CoreLocation
import Combine
import os

@MainActor
class LocationService: NSObject, ObservableObject {
    static let shared = LocationService()

    // MARK: - Published State

    @Published var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published var lastCity: String?
    @Published var lastState: String?
    @Published var lastCountry: String?
    @Published var isTracking = false
    @Published var lastUpdateTime: Date?

    // MARK: - Private

    private let locationManager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private let api = APIClient.shared
    private let logger = Logger(subsystem: "dev.malibupoint.jarvis", category: "Location")

    private var lastPostedLocation: CLLocation?
    private var lastPostTime: Date?
    private var foregroundTimer: Timer?

    /// Minimum interval between location POSTs (seconds)
    private let throttleInterval: TimeInterval = 300 // 5 minutes

    /// Minimum distance change to trigger a new POST (meters)
    private let minimumDistanceChange: CLLocationDistance = 100

    // UserDefaults keys
    private enum DefaultsKey {
        static let lastLatitude = "jarvis_location_lat"
        static let lastLongitude = "jarvis_location_lng"
        static let lastCity = "jarvis_location_city"
        static let lastState = "jarvis_location_state"
        static let lastCountry = "jarvis_location_country"
        static let lastUpdateTimestamp = "jarvis_location_timestamp"
    }

    // MARK: - Init

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        locationManager.allowsBackgroundLocationUpdates = true
        locationManager.pausesLocationUpdatesAutomatically = false
        locationManager.showsBackgroundLocationIndicator = false

        restoreLastKnownLocation()
    }

    // MARK: - Public API

    /// Request always-on location authorization and begin tracking.
    func startTracking() {
        logger.info("Requesting location authorization")

        switch locationManager.authorizationStatus {
        case .notDetermined:
            locationManager.requestAlwaysAuthorization()
        case .authorizedWhenInUse:
            // Escalate to always
            locationManager.requestAlwaysAuthorization()
        case .authorizedAlways:
            beginMonitoring()
        case .denied, .restricted:
            logger.warning("Location access denied or restricted")
        @unknown default:
            break
        }
    }

    /// Stop all location monitoring.
    func stopTracking() {
        logger.info("Stopping location tracking")
        locationManager.stopMonitoringSignificantLocationChanges()
        locationManager.stopUpdatingLocation()
        foregroundTimer?.invalidate()
        foregroundTimer = nil
        isTracking = false
    }

    /// Call when app enters foreground to supplement with standard updates.
    func enterForeground() {
        guard authorizationStatus == .authorizedAlways
           || authorizationStatus == .authorizedWhenInUse else { return }

        logger.debug("Entering foreground — starting periodic updates")
        locationManager.startUpdatingLocation()

        // Periodic foreground refresh every 5 minutes
        foregroundTimer?.invalidate()
        foregroundTimer = Timer.scheduledTimer(withTimeInterval: throttleInterval, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.locationManager.requestLocation()
            }
        }
    }

    /// Call when app enters background — rely on significant change only.
    func enterBackground() {
        logger.debug("Entering background — stopping standard updates")
        locationManager.stopUpdatingLocation()
        foregroundTimer?.invalidate()
        foregroundTimer = nil
    }

    // MARK: - Private Methods

    private func beginMonitoring() {
        logger.info("Beginning significant location change monitoring")
        locationManager.startMonitoringSignificantLocationChanges()
        locationManager.startUpdatingLocation()
        isTracking = true

        // Request an immediate location
        locationManager.requestLocation()
    }

    private func processLocation(_ location: CLLocation) {
        // Throttle: skip if we posted recently and haven't moved enough
        if let lastPost = lastPostTime,
           Date().timeIntervalSince(lastPost) < throttleInterval {
            if let lastLoc = lastPostedLocation,
               location.distance(from: lastLoc) < minimumDistanceChange {
                logger.debug("Skipping — throttled (last post \(Int(Date().timeIntervalSince(lastPost)))s ago, moved \(Int(location.distance(from: lastLoc)))m)")
                return
            }
        }

        // Reverse geocode, then POST
        geocoder.cancelGeocode()
        geocoder.reverseGeocodeLocation(location) { [weak self] placemarks, error in
            Task { @MainActor [weak self] in
                guard let self else { return }

                if let error {
                    self.logger.error("Geocode error: \(error.localizedDescription)")
                }

                let placemark = placemarks?.first
                let city = placemark?.locality ?? self.lastCity ?? "Unknown"
                let state = placemark?.administrativeArea ?? self.lastState ?? "Unknown"
                let country = placemark?.country ?? self.lastCountry ?? "Unknown"

                await self.postLocation(
                    latitude: location.coordinate.latitude,
                    longitude: location.coordinate.longitude,
                    city: city,
                    state: state,
                    country: country
                )

                self.lastPostedLocation = location
                self.lastPostTime = Date()
                self.lastCity = city
                self.lastState = state
                self.lastCountry = country
                self.lastUpdateTime = Date()

                self.saveLastKnownLocation(
                    latitude: location.coordinate.latitude,
                    longitude: location.coordinate.longitude,
                    city: city,
                    state: state,
                    country: country
                )
            }
        }
    }

    private func postLocation(
        latitude: Double,
        longitude: Double,
        city: String,
        state: String,
        country: String
    ) async {
        let payload = LocationUpdate(
            latitude: latitude,
            longitude: longitude,
            city: city,
            state: state,
            country: country
        )

        do {
            try await api.requestVoid(
                JARVISConfig.Auth.location,
                method: "POST",
                body: payload
            )
            logger.info("Posted location: \(city), \(state) (\(latitude), \(longitude))")
        } catch {
            logger.error("Failed to post location: \(error.localizedDescription)")
        }
    }

    // MARK: - UserDefaults Persistence

    private func saveLastKnownLocation(
        latitude: Double,
        longitude: Double,
        city: String,
        state: String,
        country: String
    ) {
        let defaults = UserDefaults.standard
        defaults.set(latitude, forKey: DefaultsKey.lastLatitude)
        defaults.set(longitude, forKey: DefaultsKey.lastLongitude)
        defaults.set(city, forKey: DefaultsKey.lastCity)
        defaults.set(state, forKey: DefaultsKey.lastState)
        defaults.set(country, forKey: DefaultsKey.lastCountry)
        defaults.set(Date().timeIntervalSince1970, forKey: DefaultsKey.lastUpdateTimestamp)
    }

    private func restoreLastKnownLocation() {
        let defaults = UserDefaults.standard
        lastCity = defaults.string(forKey: DefaultsKey.lastCity)
        lastState = defaults.string(forKey: DefaultsKey.lastState)
        lastCountry = defaults.string(forKey: DefaultsKey.lastCountry)

        if defaults.double(forKey: DefaultsKey.lastUpdateTimestamp) > 0 {
            lastUpdateTime = Date(timeIntervalSince1970: defaults.double(forKey: DefaultsKey.lastUpdateTimestamp))
        }

        if defaults.double(forKey: DefaultsKey.lastLatitude) != 0 {
            lastPostedLocation = CLLocation(
                latitude: defaults.double(forKey: DefaultsKey.lastLatitude),
                longitude: defaults.double(forKey: DefaultsKey.lastLongitude)
            )
        }
    }
}

// MARK: - CLLocationManagerDelegate

extension LocationService: CLLocationManagerDelegate {
    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        Task { @MainActor [weak self] in
            self?.processLocation(location)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let nsError = error as NSError
        // Ignore location-unknown errors (transient)
        if nsError.domain == kCLErrorDomain && nsError.code == CLError.locationUnknown.rawValue {
            return
        }

        Task { @MainActor [weak self] in
            self?.logger.error("Location manager error: \(error.localizedDescription)")
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus

        Task { @MainActor [weak self] in
            guard let self else { return }
            self.authorizationStatus = status
            self.logger.info("Authorization changed: \(String(describing: status.rawValue))")

            switch status {
            case .authorizedAlways, .authorizedWhenInUse:
                self.beginMonitoring()
            case .denied, .restricted:
                self.stopTracking()
            case .notDetermined:
                break
            @unknown default:
                break
            }
        }
    }
}
