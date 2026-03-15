import SwiftUI
import UserNotifications
import HealthKit
import Contacts
import MusicKit

struct SettingsView: View {
    @Binding var isShowing: Bool
    @EnvironmentObject var authVM: AuthViewModel
    @EnvironmentObject var chatVM: ChatViewModel
    @StateObject private var eventKit = EventKitService.shared
    @StateObject private var onDeviceLLM = OnDeviceLLMService.shared
    @State private var serverURL = JARVISConfig.baseURL
    @State private var healthStatus: HealthAuthStatus = .unknown
    @State private var notificationStatus: NotificationAuthStatus = .unknown
    @State private var contactsStatus: ContactsAuthStatus = .unknown
    @State private var musicStatus: MusicAuthStatus = .unknown
    @State private var isLoadingProviders = false
    @State private var showDeleteModelConfirm = false

    enum HealthAuthStatus {
        case unknown, authorized, denied, unavailable, syncing
        var label: String {
            switch self {
            case .unknown: return "NOT DETERMINED"
            case .authorized: return "AUTHORIZED"
            case .denied: return "DENIED"
            case .unavailable: return "UNAVAILABLE"
            case .syncing: return "SYNCING"
            }
        }
        var isGranted: Bool { self == .authorized || self == .syncing }
    }

    enum NotificationAuthStatus {
        case unknown, authorized, denied, provisional
        var label: String {
            switch self {
            case .unknown: return "NOT DETERMINED"
            case .authorized: return "AUTHORIZED"
            case .denied: return "DENIED"
            case .provisional: return "PROVISIONAL"
            }
        }
        var isGranted: Bool { self == .authorized || self == .provisional }
    }

    enum ContactsAuthStatus {
        case unknown, authorized, denied, restricted
        var label: String {
            switch self {
            case .unknown: return "NOT DETERMINED"
            case .authorized: return "AUTHORIZED"
            case .denied: return "DENIED"
            case .restricted: return "RESTRICTED"
            }
        }
        var isGranted: Bool { self == .authorized }
    }

    enum MusicAuthStatus {
        case unknown, authorized, denied, restricted
        var label: String {
            switch self {
            case .unknown: return "NOT DETERMINED"
            case .authorized: return "AUTHORIZED"
            case .denied: return "DENIED"
            case .restricted: return "RESTRICTED"
            }
        }
        var isGranted: Bool { self == .authorized }
    }

    var body: some View {
        ZStack(alignment: .trailing) {
            Color.black.opacity(0.4)
                .ignoresSafeArea()
                .onTapGesture { isShowing = false }

            VStack(spacing: 0) {
                // Header
                HStack {
                    Text("SETTINGS")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue)

                    Spacer()

                    Button { isShowing = false } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)

                Rectangle()
                    .fill(Color.jarvisBlue.opacity(0.1))
                    .frame(height: 0.5)

                ScrollView {
                    VStack(spacing: 20) {
                        // User Info
                        if let user = authVM.user {
                            SettingsSection(title: "IDENTITY") {
                                SettingsRow(label: "User", value: user.username)
                                SettingsRow(label: "Email", value: user.email)
                            }
                        }

                        // Model Provider
                        SettingsSection(title: "AI PROVIDER") {
                            if isLoadingProviders {
                                HStack {
                                    ProgressView()
                                        .scaleEffect(0.7)
                                        .tint(.jarvisBlue)
                                    Text("Loading providers...")
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.jarvisTextDim)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                            } else if chatVM.availableProviders.isEmpty {
                                HStack {
                                    Image(systemName: "exclamationmark.triangle")
                                        .font(.system(size: 11))
                                        .foregroundColor(.jarvisGold)
                                    Text("No providers available")
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.jarvisTextDim)
                                    Spacer()
                                    Button {
                                        Task {
                                            isLoadingProviders = true
                                            await chatVM.loadProviders()
                                            isLoadingProviders = false
                                        }
                                    } label: {
                                        Text("RETRY")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                    }
                                }
                                .padding(.vertical, 4)
                            } else {
                                ForEach(chatVM.availableProviders) { provider in
                                    Button {
                                        chatVM.selectedProvider = provider.id
                                    } label: {
                                        HStack {
                                            Circle()
                                                .fill(
                                                    provider.available
                                                        ? Color.jarvisOnline
                                                        : Color.jarvisError.opacity(0.5)
                                                )
                                                .frame(width: 5, height: 5)

                                            Text(provider.id.uppercased())
                                                .font(.system(size: 12, weight: .medium, design: .monospaced))
                                                .foregroundColor(
                                                    chatVM.selectedProvider == provider.id
                                                        ? .jarvisBlue
                                                        : .jarvisText
                                                )

                                            Spacer()

                                            if chatVM.selectedProvider == provider.id {
                                                Image(systemName: "checkmark")
                                                    .font(.system(size: 10, weight: .bold))
                                                    .foregroundColor(.jarvisBlue)
                                            }

                                            if !provider.available {
                                                Text("OFFLINE")
                                                    .font(.system(size: 8, design: .monospaced))
                                                    .foregroundColor(.jarvisError.opacity(0.6))
                                            }
                                        }
                                        .padding(.vertical, 4)
                                    }
                                    .disabled(!provider.available)
                                }
                            }
                        }

                        // Server
                        SettingsSection(title: "CONNECTION") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("SERVER URL")
                                    .hudLabel()

                                TextField("https://app.malibupoint.dev", text: $serverURL)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(.jarvisText)
                                    .tint(.jarvisBlue)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background {
                                        HexCornerShape(cutSize: 6)
                                            .fill(Color.jarvisBlue.opacity(0.03))
                                            .overlay {
                                                HexCornerShape(cutSize: 6)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.1), lineWidth: 0.5)
                                            }
                                    }
                                    .onSubmit {
                                        UserDefaults.standard.set(serverURL, forKey: "jarvis_base_url")
                                    }
                            }
                        }

                        // Device Integrations
                        SettingsSection(title: "DEVICE INTEGRATIONS") {
                            // Reminders
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("Reminders")
                                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                                        .foregroundColor(.jarvisText)

                                    Text(EventKitService.statusText(for: eventKit.reminderAuthStatus).uppercased())
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            EventKitService.isAuthorized(eventKit.reminderAuthStatus)
                                                ? .jarvisOnline
                                                : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !EventKitService.isAuthorized(eventKit.reminderAuthStatus) {
                                    Button {
                                        Task { await eventKit.requestReminderAccess() }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Calendar
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("Calendar")
                                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                                        .foregroundColor(.jarvisText)

                                    Text(EventKitService.statusText(for: eventKit.calendarAuthStatus).uppercased())
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            EventKitService.isAuthorized(eventKit.calendarAuthStatus)
                                                ? .jarvisOnline
                                                : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !EventKitService.isAuthorized(eventKit.calendarAuthStatus) {
                                    Button {
                                        Task { await eventKit.requestCalendarAccess() }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Health
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "heart.fill")
                                            .font(.system(size: 11))
                                            .foregroundColor(.red)
                                        Text("Apple Health")
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                    }

                                    Text(healthStatus.label)
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            healthStatus.isGranted ? .jarvisOnline : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !healthStatus.isGranted && healthStatus != .unavailable {
                                    Button {
                                        Task {
                                            let service = HealthSyncService.shared
                                            let authorized = await service.requestAuthorization()
                                            healthStatus = authorized ? .authorized : .denied
                                            if authorized {
                                                healthStatus = .syncing
                                                await service.startBackgroundSync()
                                                healthStatus = .authorized
                                            }
                                        }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else if healthStatus.isGranted {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Notifications
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "bell.fill")
                                            .font(.system(size: 11))
                                            .foregroundColor(.jarvisGold)
                                        Text("Notifications")
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                    }

                                    Text(notificationStatus.label)
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            notificationStatus.isGranted ? .jarvisOnline : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !notificationStatus.isGranted {
                                    Button {
                                        Task {
                                            let center = UNUserNotificationCenter.current()
                                            do {
                                                let granted = try await center.requestAuthorization(
                                                    options: [.alert, .badge, .sound]
                                                )
                                                await refreshNotificationStatus()
                                                if !granted {
                                                    notificationStatus = .denied
                                                }
                                            } catch {
                                                notificationStatus = .denied
                                            }
                                        }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Contacts
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "person.crop.circle.fill")
                                            .font(.system(size: 11))
                                            .foregroundColor(.jarvisBlue)
                                        Text("Contacts")
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                    }

                                    Text(contactsStatus.label)
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            contactsStatus.isGranted ? .jarvisOnline : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !contactsStatus.isGranted && contactsStatus != .restricted {
                                    Button {
                                        Task {
                                            let granted = await ContactsService.shared.requestAccess()
                                            refreshContactsStatus()
                                            if !granted {
                                                contactsStatus = .denied
                                            }
                                        }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else if contactsStatus.isGranted {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Music Library
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "music.note")
                                            .font(.system(size: 11))
                                            .foregroundColor(.purple)
                                        Text("Music Library")
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                    }

                                    Text(musicStatus.label)
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(
                                            musicStatus.isGranted ? .jarvisOnline : .jarvisTextDim
                                        )
                                }

                                Spacer()

                                if !musicStatus.isGranted && musicStatus != .restricted {
                                    Button {
                                        Task {
                                            let granted = await MusicService.shared.requestAccess()
                                            refreshMusicStatus()
                                            if !granted {
                                                musicStatus = .denied
                                            }
                                        }
                                    } label: {
                                        Text("CONNECT")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 5)
                                            .background {
                                                HexCornerShape(cutSize: 4)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                            }
                                    }
                                } else if musicStatus.isGranted {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)
                        }

                        // On-Device AI
                        SettingsSection(title: "ON-DEVICE AI") {
                            // Model info header
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "brain")
                                            .font(.system(size: 11))
                                            .foregroundColor(.jarvisBlue)
                                        Text(OnDeviceLLMService.modelDisplayName)
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                    }

                                    Text(onDeviceLLM.state.label)
                                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                                        .foregroundColor(stateColor(for: onDeviceLLM.state))
                                }

                                Spacer()

                                if case .ready = onDeviceLLM.state {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.jarvisOnline)
                                }
                            }
                            .padding(.vertical, 2)

                            // Download progress bar
                            if case .downloading(let progress) = onDeviceLLM.state {
                                VStack(spacing: 4) {
                                    GeometryReader { geo in
                                        ZStack(alignment: .leading) {
                                            HexCornerShape(cutSize: 3)
                                                .fill(Color.jarvisBlue.opacity(0.1))
                                                .frame(height: 6)

                                            HexCornerShape(cutSize: 3)
                                                .fill(Color.jarvisBlue.opacity(0.7))
                                                .frame(width: max(0, geo.size.width * progress), height: 6)
                                        }
                                    }
                                    .frame(height: 6)

                                    HStack {
                                        Text("\(Int(progress * 100))%")
                                            .font(.system(size: 9, design: .monospaced))
                                            .foregroundColor(.jarvisTextDim)
                                        Spacer()
                                        Text("~\(OnDeviceLLMService.estimatedSizeMB) MB")
                                            .font(.system(size: 9, design: .monospaced))
                                            .foregroundColor(.jarvisTextDim)
                                    }
                                }
                                .padding(.vertical, 2)
                            }

                            // Storage display
                            if let size = onDeviceLLM.modelSizeOnDisk {
                                SettingsRow(label: "Storage", value: size)
                            }

                            // Action buttons
                            switch onDeviceLLM.state {
                            case .notDownloaded:
                                Button {
                                    Task { await onDeviceLLM.downloadModel() }
                                } label: {
                                    HStack {
                                        Image(systemName: "arrow.down.circle")
                                            .font(.system(size: 11))
                                        Text("DOWNLOAD MODEL")
                                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                    }
                                    .foregroundColor(.jarvisBlue)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 36)
                                    .background {
                                        HexCornerShape(cutSize: 5)
                                            .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                    }
                                }
                                .padding(.top, 4)

                            case .downloading:
                                Text("Downloading model files...")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundColor(.jarvisTextDim)
                                    .frame(maxWidth: .infinity, alignment: .center)
                                    .padding(.top, 2)

                            case .downloaded:
                                HStack(spacing: 8) {
                                    Button {
                                        Task { try? await onDeviceLLM.loadModel() }
                                    } label: {
                                        HStack {
                                            Image(systemName: "bolt.fill")
                                                .font(.system(size: 10))
                                            Text("LOAD")
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .tracking(1)
                                        }
                                        .foregroundColor(.jarvisBlue)
                                        .frame(maxWidth: .infinity)
                                        .frame(height: 36)
                                        .background {
                                            HexCornerShape(cutSize: 5)
                                                .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 0.5)
                                        }
                                    }

                                    Button {
                                        showDeleteModelConfirm = true
                                    } label: {
                                        HStack {
                                            Image(systemName: "trash")
                                                .font(.system(size: 10))
                                            Text("DELETE")
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .tracking(1)
                                        }
                                        .foregroundColor(.jarvisError)
                                        .frame(maxWidth: .infinity)
                                        .frame(height: 36)
                                        .background {
                                            HexCornerShape(cutSize: 5)
                                                .strokeBorder(Color.jarvisError.opacity(0.3), lineWidth: 0.5)
                                        }
                                    }
                                }
                                .padding(.top, 4)

                            case .loading:
                                HStack {
                                    ProgressView()
                                        .scaleEffect(0.7)
                                        .tint(.jarvisBlue)
                                    Text("Loading model...")
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundColor(.jarvisTextDim)
                                    Spacer()
                                }
                                .padding(.top, 2)

                            case .ready:
                                HStack(spacing: 8) {
                                    Button {
                                        onDeviceLLM.unloadModel()
                                    } label: {
                                        HStack {
                                            Image(systemName: "eject.fill")
                                                .font(.system(size: 10))
                                            Text("UNLOAD")
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .tracking(1)
                                        }
                                        .foregroundColor(.jarvisGold)
                                        .frame(maxWidth: .infinity)
                                        .frame(height: 36)
                                        .background {
                                            HexCornerShape(cutSize: 5)
                                                .strokeBorder(Color.jarvisGold.opacity(0.3), lineWidth: 0.5)
                                        }
                                    }

                                    Button {
                                        showDeleteModelConfirm = true
                                    } label: {
                                        HStack {
                                            Image(systemName: "trash")
                                                .font(.system(size: 10))
                                            Text("DELETE")
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .tracking(1)
                                        }
                                        .foregroundColor(.jarvisError)
                                        .frame(maxWidth: .infinity)
                                        .frame(height: 36)
                                        .background {
                                            HexCornerShape(cutSize: 5)
                                                .strokeBorder(Color.jarvisError.opacity(0.3), lineWidth: 0.5)
                                        }
                                    }
                                }
                                .padding(.top, 4)

                            case .error(let msg):
                                VStack(spacing: 6) {
                                    Text(msg)
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundColor(.jarvisError)
                                        .lineLimit(2)
                                        .frame(maxWidth: .infinity, alignment: .leading)

                                    Button {
                                        onDeviceLLM.refreshState()
                                    } label: {
                                        Text("RETRY")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .tracking(1)
                                            .foregroundColor(.jarvisBlue)
                                    }
                                }
                                .padding(.top, 2)
                            }

                            // Prefer on-device toggle
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Prefer On-Device")
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.jarvisText)
                                    Text("Use local model when available")
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundColor(.jarvisTextDim)
                                }

                                Spacer()

                                Toggle("", isOn: $onDeviceLLM.preferOnDevice)
                                    .labelsHidden()
                                    .tint(.jarvisBlue)
                            }
                            .padding(.top, 4)

                            // Info line
                            Text("Offline AI via MLX. ~\(OnDeviceLLMService.estimatedSizeMB) MB on-device.")
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.jarvisTextDim.opacity(0.6))
                                .padding(.top, 2)
                        }
                        .alert("Delete Model", isPresented: $showDeleteModelConfirm) {
                            Button("Delete", role: .destructive) {
                                onDeviceLLM.deleteModel()
                            }
                            Button("Cancel", role: .cancel) {}
                        } message: {
                            Text("This will remove the downloaded model files and free up ~\(OnDeviceLLMService.estimatedSizeMB) MB of storage.")
                        }

                        // About
                        SettingsSection(title: "SYSTEM") {
                            SettingsRow(label: "Version", value: "1.0.0")
                            SettingsRow(label: "Protocol", value: "JARVIS v1")
                            SettingsRow(label: "Encryption", value: "AES-256")
                        }

                        // Logout
                        Button {
                            Task {
                                await authVM.logout()
                                isShowing = false
                            }
                        } label: {
                            Text("DISCONNECT")
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .tracking(2)
                                .foregroundColor(.jarvisError)
                                .frame(maxWidth: .infinity)
                                .frame(height: 44)
                                .background {
                                    HexCornerShape(cutSize: 6)
                                        .fill(Color.jarvisError.opacity(0.05))
                                        .overlay {
                                            HexCornerShape(cutSize: 6)
                                                .strokeBorder(Color.jarvisError.opacity(0.2), lineWidth: 0.5)
                                        }
                                }
                        }
                    }
                    .padding(16)
                }
            }
            .frame(width: 300)
            .background {
                Rectangle()
                    .fill(.ultraThinMaterial)
                    .overlay {
                        Rectangle()
                            .fill(Color.jarvisDeepDark.opacity(0.85))
                    }
                    .overlay(alignment: .leading) {
                        Rectangle()
                            .fill(Color.jarvisBlue.opacity(0.08))
                            .frame(width: 0.5)
                    }
                    .ignoresSafeArea()
            }
            .task {
                isLoadingProviders = true
                await chatVM.loadProviders()
                isLoadingProviders = false
                refreshHealthStatus()
                refreshContactsStatus()
                refreshMusicStatus()
                await refreshNotificationStatus()
            }
        }
    }

    // MARK: - On-Device Model Helpers

    private func stateColor(for state: OnDeviceLLMService.ModelState) -> Color {
        switch state {
        case .notDownloaded: return .jarvisTextDim
        case .downloading: return .jarvisGold
        case .downloaded: return .jarvisBlue
        case .loading: return .jarvisGold
        case .ready: return .jarvisOnline
        case .error: return .jarvisError
        }
    }

    // MARK: - Status Helpers

    private func refreshHealthStatus() {
        guard HKHealthStore.isHealthDataAvailable() else {
            healthStatus = .unavailable
            return
        }
        // HealthKit intentionally hides READ authorization status for privacy.
        // authorizationStatus(for:) only checks WRITE/share status.
        // Since we only request read access, we can't know for sure.
        // Check if HealthSyncService is running as a proxy for "connected".
        let service = HealthSyncService.shared
        if service.isRunning {
            healthStatus = .authorized
        } else {
            // Try a test query — if it returns data, we're authorized
            healthStatus = .unknown
        }
    }

    private func refreshNotificationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized:
            notificationStatus = .authorized
        case .denied:
            notificationStatus = .denied
        case .provisional:
            notificationStatus = .provisional
        case .notDetermined:
            notificationStatus = .unknown
        case .ephemeral:
            notificationStatus = .authorized
        @unknown default:
            notificationStatus = .unknown
        }
    }

    private func refreshContactsStatus() {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized:
            contactsStatus = .authorized
        case .denied:
            contactsStatus = .denied
        case .restricted:
            contactsStatus = .restricted
        case .notDetermined:
            contactsStatus = .unknown
        @unknown default:
            contactsStatus = .unknown
        }
    }

    private func refreshMusicStatus() {
        switch MusicAuthorization.currentStatus {
        case .authorized:
            musicStatus = .authorized
        case .denied:
            musicStatus = .denied
        case .restricted:
            musicStatus = .restricted
        case .notDetermined:
            musicStatus = .unknown
        @unknown default:
            musicStatus = .unknown
        }
    }
}

// MARK: - Settings Components

struct SettingsSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .tracking(2)
                .foregroundColor(.jarvisBlue.opacity(0.5))

            VStack(spacing: 6) {
                content
            }
            .padding(12)
            .glassBackground(opacity: 0.3, cutSize: 8)
            .hudAccentCorners(cutSize: 8, opacity: 0.25, lineLength: 10)
        }
    }
}

struct SettingsRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.jarvisTextDim)

            Spacer()

            Text(value)
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .foregroundColor(.jarvisText)
                .lineLimit(1)
        }
    }
}
