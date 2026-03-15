import Contacts
import os

actor ContactsService {
    static let shared = ContactsService()

    private let store = CNContactStore()
    private let logger = Logger(subsystem: "dev.jarvis.malibupoint", category: "Contacts")

    var isAuthorized: Bool {
        CNContactStore.authorizationStatus(for: .contacts) == .authorized
    }

    var authorizationStatus: CNAuthorizationStatus {
        CNContactStore.authorizationStatus(for: .contacts)
    }

    func requestAccess() async -> Bool {
        do {
            let granted = try await store.requestAccess(for: .contacts)
            logger.info("Contacts access \(granted ? "granted" : "denied")")
            return granted
        } catch {
            logger.error("Contacts access request failed: \(error.localizedDescription)")
            return false
        }
    }

    func fetchAllContacts() async throws -> [CNContact] {
        let keys: [CNKeyDescriptor] = [
            CNContactGivenNameKey, CNContactFamilyNameKey,
            CNContactPhoneNumbersKey, CNContactEmailAddressesKey,
            CNContactPostalAddressesKey, CNContactOrganizationNameKey,
            CNContactImageDataKey, CNContactThumbnailImageDataKey,
        ] as [CNKeyDescriptor]

        var contacts: [CNContact] = []
        let request = CNContactFetchRequest(keysToFetch: keys)
        try store.enumerateContacts(with: request) { contact, _ in
            contacts.append(contact)
        }
        return contacts
    }

    /// Sync contacts to JARVIS backend via /api/v1/contacts/sync
    func syncToBackend() async throws {
        let contacts = try await fetchAllContacts()
        logger.info("Syncing \(contacts.count) contacts to backend")

        var payload: [[String: Any]] = []
        for contact in contacts {
            var entry: [String: Any] = [
                "first_name": contact.givenName,
                "last_name": contact.familyName,
            ]

            if let phone = contact.phoneNumbers.first?.value.stringValue {
                entry["phone"] = phone
            }
            if let email = contact.emailAddresses.first?.value as String? {
                entry["email"] = email
            }
            if !contact.organizationName.isEmpty {
                entry["company"] = contact.organizationName
            }
            if let address = contact.postalAddresses.first?.value {
                entry["street"] = address.street
                entry["city"] = address.city
                entry["state"] = address.state
                entry["postal_code"] = address.postalCode
                entry["country"] = address.country
            }

            payload.append(entry)
        }

        // POST to backend contacts sync endpoint
        let jsonData = try JSONSerialization.data(withJSONObject: payload)
        guard let url = URL(string: JARVISConfig.Contacts.list) else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = await APIClient.shared.getAccessToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = jsonData
        _ = try await URLSession.shared.data(for: request)

        logger.info("Synced \(contacts.count) contacts to backend")
    }
}
