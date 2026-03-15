import SwiftUI
import MapKit

// MARK: - Atlas Contact Model

struct AtlasContact: Identifiable, Equatable {
    let id: String
    let name: String
    let phone: String?
    let email: String?
    let address: String?
    let company: String?
    let city: String?
    let state: String?
    let coordinate: CLLocationCoordinate2D
    let photoBase64: String?
    let photoContentType: String?

    var initials: String {
        let parts = name.split(separator: " ")
        let first = parts.first.map { String($0.prefix(1)) } ?? ""
        let last = parts.count > 1 ? String(parts.last!.prefix(1)) : ""
        return (first + last).uppercased()
    }

    var decodedPhoto: UIImage? {
        guard let base64 = photoBase64,
              !base64.isEmpty,
              !base64.hasPrefix("http"),
              let data = Data(base64Encoded: base64) else { return nil }
        return UIImage(data: data)
    }

    static func == (lhs: AtlasContact, rhs: AtlasContact) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Search Result Annotation

private struct SearchResultAnnotation: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let coordinate: CLLocationCoordinate2D

    static func == (lhs: SearchResultAnnotation, rhs: SearchResultAnnotation) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - API Response Model

private struct ContactAPIResponse: Codable {
    let id: String
    let first_name: String
    let last_name: String?
    let phone: String?
    let email: String?
    let company: String?
    let address: String?
    let street: String?
    let city: String?
    let state: String?
    let postal_code: String?
    let country: String?
    let photo: String?
    let photo_content_type: String?

    var fullName: String {
        [first_name, last_name].compactMap { $0 }.joined(separator: " ")
    }

    var fullAddress: String? {
        if let address, !address.isEmpty { return address }
        let parts = [street, city, state, postal_code, country].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }
}

// MARK: - Atlas Map View

struct AtlasMapView: View {
    @Binding var isShowing: Bool
    @State private var position: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 40.29, longitude: -111.69),
            span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)
        )
    )
    @State private var contacts: [AtlasContact] = []
    @State private var selectedContact: AtlasContact?
    @State private var searchText = ""
    @State private var searchResults: [MKMapItem] = []
    @State private var selectedSearchResult: SearchResultAnnotation?
    @State private var isLoading = true
    @FocusState private var isSearchFocused: Bool
    @State private var errorMessage: String?
    @State private var geocodedCount = 0
    @State private var totalToGeocode = 0

    // Group contacts by coordinate (same address → single pin with count)
    private var contactGroups: [(key: String, contacts: [AtlasContact])] {
        var groups: [String: [AtlasContact]] = [:]
        for contact in contacts {
            let key = "\(String(format: "%.4f", contact.coordinate.latitude)),\(String(format: "%.4f", contact.coordinate.longitude))"
            groups[key, default: []].append(contact)
        }
        return groups.map { (key: $0.key, contacts: $0.value) }
    }

    private var searchResultAnnotations: [SearchResultAnnotation] {
        searchResults.compactMap { item in
            guard let location = item.placemark.location else { return nil }
            return SearchResultAnnotation(
                name: item.name ?? "Location",
                coordinate: location.coordinate
            )
        }
    }

    var body: some View {
        ZStack {
            Color.jarvisDeepDark.ignoresSafeArea()

            // Map
            Map(position: $position, selection: Binding<String?>(
                get: { selectedContact?.id },
                set: { newId in
                    selectedContact = contacts.first { $0.id == newId }
                }
            )) {
                // Contact markers (grouped by location)
                ForEach(contactGroups, id: \.key) { group in
                    let displayContact = group.contacts.first(where: { $0.id == selectedContact?.id }) ?? group.contacts[0]
                    Annotation(displayContact.name, coordinate: displayContact.coordinate) {
                        contactGroupPin(contacts: group.contacts, displayContact: displayContact)
                    }
                    .tag(displayContact.id)
                }

                // Search result markers
                ForEach(searchResultAnnotations, id: \.id) { result in
                    Marker(
                        result.name,
                        systemImage: "mappin",
                        coordinate: result.coordinate
                    )
                    .tint(Color.jarvisGold)
                }

                // Selected search result pin
                if let pinned = selectedSearchResult {
                    Marker(
                        pinned.name,
                        systemImage: "mappin.circle.fill",
                        coordinate: pinned.coordinate
                    )
                    .tint(Color.jarvisGold)
                }
            }
            .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll))
            .mapControls {
                MapCompass()
                MapScaleView()
                MapUserLocationButton()
            }
            .ignoresSafeArea(edges: .bottom)

            // Overlays
            VStack(spacing: 0) {
                // Top bar: close + search
                topBar
                    .padding(.horizontal, 12)
                    .padding(.top, 8)

                Spacer()

                // Bottom: panels above search bar
                VStack(spacing: 8) {
                    if let error = errorMessage {
                        errorBanner(error)
                    }

                    if isLoading {
                        loadingIndicator
                    } else if let selected = selectedContact {
                        contactDetailPanel(selected)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                            .padding(.horizontal, 12)
                    } else if let result = selectedSearchResult {
                        searchResultDetailPanel(result)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                            .padding(.horizontal, 12)
                    }

                    // Search results (top 3) above search bar
                    if !searchResults.isEmpty {
                        VStack(spacing: 4) {
                            ForEach(Array(searchResults.prefix(3).enumerated()), id: \.offset) { _, result in
                                Button {
                                    selectedContact = nil
                                    isSearchFocused = false
                                    let coord = result.placemark.coordinate
                                    let annotation = SearchResultAnnotation(
                                        name: result.name ?? "Location",
                                        coordinate: coord
                                    )
                                    selectedSearchResult = annotation
                                    withAnimation(.easeInOut(duration: 0.5)) {
                                        position = .region(MKCoordinateRegion(
                                            center: coord,
                                            span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                                        ))
                                    }
                                    searchResults = []
                                    searchText = ""
                                } label: {
                                    HStack {
                                        Image(systemName: "mappin")
                                            .font(.system(size: 10))
                                            .foregroundColor(.jarvisGold)
                                        Text(result.name ?? "Unknown")
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundColor(.jarvisText)
                                            .lineLimit(1)
                                        Spacer()
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background {
                                        HexCornerShape(cutSize: 4)
                                            .fill(Color.jarvisPanelBg.opacity(0.8))
                                    }
                                }
                            }
                        }
                        .padding(.horizontal, 12)
                    }

                    // Search bar at very bottom
                    searchBar
                        .padding(.horizontal, 12)
                }
                .padding(.bottom, 16)
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.85), value: selectedContact)
        .animation(.spring(response: 0.35, dampingFraction: 0.85), value: selectedSearchResult)
        .animation(.easeInOut(duration: 0.3), value: isLoading)
        .task {
            await loadContacts()
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(spacing: 10) {
            // Close button
            Button {
                isShowing = false
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.jarvisBlue.opacity(0.7))
                    .frame(width: 34, height: 34)
                    .background {
                        HexCornerShape(cutSize: 6)
                            .fill(Color.jarvisPanelBg.opacity(0.8))
                            .overlay {
                                HexCornerShape(cutSize: 6)
                                    .strokeBorder(Color.jarvisBlue.opacity(0.2), lineWidth: 0.5)
                            }
                    }
            }
            .padding(.top, 8)
            .padding(.leading, 4)

            // ATLAS label
            Text("A.T.L.A.S.")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .tracking(3)
                .foregroundColor(.jarvisBlue.opacity(0.8))

            Spacer()
        }
    }

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 12))
                .foregroundColor(.jarvisBlue.opacity(0.5))

            TextField("", text: $searchText, prompt: Text("Search places...")
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.jarvisTextDim.opacity(0.4)))
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.jarvisText)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .focused($isSearchFocused)
                .onSubmit {
                    Task { await search() }
                }
                .onChange(of: isSearchFocused) { focused in
                    if focused {
                        selectedContact = nil
                        selectedSearchResult = nil
                    }
                }

            if !searchText.isEmpty {
                Button {
                    searchText = ""
                    searchResults = []
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(.jarvisTextDim.opacity(0.4))
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 10)
        .background {
            HexCornerShape(cutSize: 6)
                .fill(.ultraThinMaterial)
                .overlay {
                    HexCornerShape(cutSize: 6)
                        .fill(Color.jarvisPanelBg.opacity(0.6))
                }
                .overlay {
                    HexCornerShape(cutSize: 6)
                        .strokeBorder(Color.jarvisBlue.opacity(0.15), lineWidth: 0.5)
                }
        }
    }

    // Contact count removed per design request

    // MARK: - Contact Group Pin (handles multiple contacts at same address)

    private func contactGroupPin(contacts: [AtlasContact], displayContact: AtlasContact) -> some View {
        Button {
            // Cycle through contacts at this location
            if let current = selectedContact,
               let currentIdx = contacts.firstIndex(where: { $0.id == current.id }) {
                let nextIdx = (currentIdx + 1) % contacts.count
                selectedContact = contacts[nextIdx]
            } else {
                selectedContact = displayContact
            }
            selectedSearchResult = nil
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            withAnimation(.easeInOut(duration: 0.5)) {
                position = .region(MKCoordinateRegion(
                    center: displayContact.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                ))
            }
        } label: {
            let contact = contacts.first(where: { $0.id == selectedContact?.id }) ?? displayContact
            ZStack {
                HexCornerShape(cutSize: 5)
                    .fill(Color.jarvisDeepDark.opacity(0.85))
                    .overlay {
                        HexCornerShape(cutSize: 5)
                            .strokeBorder(
                                selectedContact?.id == contact.id
                                    ? Color.jarvisBlue
                                    : Color.jarvisBlue.opacity(0.4),
                                lineWidth: selectedContact?.id == contact.id ? 1.5 : 0.5
                            )
                    }
                    .frame(width: 36, height: 36)

                if let photo = contact.decodedPhoto {
                    Image(uiImage: photo)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 28, height: 28)
                        .clipShape(HexCornerShape(cutSize: 4))
                } else {
                    Text(contact.initials)
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(.jarvisBlue)
                }
            }
            .shadow(color: .jarvisBlue.opacity(selectedContact?.id == contact.id ? 0.4 : 0.15), radius: 6)
            .overlay(alignment: .topTrailing) {
                if contacts.count > 1 {
                    Text("\(contacts.count)")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundColor(.white)
                        .frame(width: 16, height: 16)
                        .background(Color.jarvisBlue)
                        .clipShape(Circle())
                        .offset(x: 6, y: -6)
                }
            }
        }
    }

    // MARK: - Contact Detail Panel

    private func contactDetailPanel(_ contact: AtlasContact) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack(spacing: 12) {
                // Photo or initials
                ZStack {
                    HexCornerShape(cutSize: 8)
                        .fill(Color.jarvisBlue.opacity(0.08))
                        .overlay {
                            HexCornerShape(cutSize: 8)
                                .strokeBorder(Color.jarvisBlue.opacity(0.2), lineWidth: 0.5)
                        }
                        .frame(width: 50, height: 50)

                    if let photo = contact.decodedPhoto {
                        Image(uiImage: photo)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 42, height: 42)
                            .clipShape(HexCornerShape(cutSize: 6))
                    } else {
                        Text(contact.initials)
                            .font(.system(size: 18, weight: .bold, design: .monospaced))
                            .foregroundColor(.jarvisBlue)
                    }
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(contact.name.uppercased())
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                        .tracking(1)
                        .foregroundColor(.jarvisText)
                        .lineLimit(1)

                    if let company = contact.company, !company.isEmpty {
                        Text(company)
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .foregroundColor(.jarvisTextDim)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Close detail
                Button {
                    selectedContact = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.jarvisTextDim)
                        .frame(width: 28, height: 28)
                        .background {
                            HexCornerShape(cutSize: 5)
                                .fill(Color.white.opacity(0.05))
                        }
                }
            }

            // Divider
            Rectangle()
                .fill(Color.jarvisBlue.opacity(0.1))
                .frame(height: 0.5)

            // Info rows
            VStack(alignment: .leading, spacing: 8) {
                if let phone = contact.phone, !phone.isEmpty {
                    infoRow(icon: "phone.fill", label: "PHONE", value: phone)
                }
                if let email = contact.email, !email.isEmpty {
                    infoRow(icon: "envelope.fill", label: "EMAIL", value: email)
                }
                if let address = contact.address, !address.isEmpty {
                    infoRow(icon: "mappin.circle.fill", label: "ADDRESS", value: address)
                }
            }

            // Action buttons
            HStack(spacing: 10) {
                if let phone = contact.phone, !phone.isEmpty {
                    actionButton(icon: "phone.fill", label: "CALL") {
                        let cleaned = phone.replacingOccurrences(of: " ", with: "")
                            .replacingOccurrences(of: "-", with: "")
                            .replacingOccurrences(of: "(", with: "")
                            .replacingOccurrences(of: ")", with: "")
                        if let url = URL(string: "tel:\(cleaned)") {
                            UIApplication.shared.open(url)
                        }
                    }
                }

                if let address = contact.address, !address.isEmpty {
                    actionButton(icon: "arrow.triangle.turn.up.right.diamond.fill", label: "NAVIGATE") {
                        let encoded = address.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
                        if let url = URL(string: "maps://?daddr=\(encoded)") {
                            UIApplication.shared.open(url)
                        }
                    }
                }

                if let email = contact.email, !email.isEmpty {
                    actionButton(icon: "envelope.fill", label: "EMAIL") {
                        if let url = URL(string: "mailto:\(email)") {
                            UIApplication.shared.open(url)
                        }
                    }
                }
            }
        }
        .padding(16)
        .glassBackground(opacity: 0.7, cutSize: 10)
        .hudAccentCorners(cutSize: 10, opacity: 0.25, lineLength: 16)
    }

    // MARK: - Search Result Detail Panel

    private func searchResultDetailPanel(_ result: SearchResultAnnotation) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                ZStack {
                    HexCornerShape(cutSize: 8)
                        .fill(Color.jarvisGold.opacity(0.08))
                        .overlay {
                            HexCornerShape(cutSize: 8)
                                .strokeBorder(Color.jarvisGold.opacity(0.2), lineWidth: 0.5)
                        }
                        .frame(width: 50, height: 50)

                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 22))
                        .foregroundColor(.jarvisGold)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(result.name.uppercased())
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                        .tracking(1)
                        .foregroundColor(.jarvisText)
                        .lineLimit(2)

                    Text(String(format: "%.4f, %.4f", result.coordinate.latitude, result.coordinate.longitude))
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundColor(.jarvisTextDim)
                }

                Spacer()

                Button {
                    selectedSearchResult = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.jarvisTextDim)
                        .frame(width: 28, height: 28)
                        .background {
                            HexCornerShape(cutSize: 5)
                                .fill(Color.white.opacity(0.05))
                        }
                }
            }

            Rectangle()
                .fill(Color.jarvisGold.opacity(0.1))
                .frame(height: 0.5)

            HStack(spacing: 10) {
                actionButton(icon: "arrow.triangle.turn.up.right.diamond.fill", label: "NAVIGATE") {
                    let coord = result.coordinate
                    if let url = URL(string: "maps://?daddr=\(coord.latitude),\(coord.longitude)") {
                        UIApplication.shared.open(url)
                    }
                }
            }
        }
        .padding(16)
        .glassBackground(opacity: 0.7, cutSize: 10)
        .hudAccentCorners(cutSize: 10, opacity: 0.25, lineLength: 16)
    }

    // MARK: - Info Row

    private func infoRow(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 10))
                .foregroundColor(.jarvisBlue.opacity(0.6))
                .frame(width: 16)

            Text(label)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .tracking(1)
                .foregroundColor(.jarvisBlue.opacity(0.5))
                .frame(width: 50, alignment: .leading)

            Text(value)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.jarvisText.opacity(0.9))
                .lineLimit(2)
        }
    }

    // MARK: - Action Button

    private func actionButton(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 10))
                Text(label)
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .tracking(1)
            }
            .foregroundColor(.jarvisBlue)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background {
                HexCornerShape(cutSize: 5)
                    .fill(Color.jarvisBlue.opacity(0.08))
                    .overlay {
                        HexCornerShape(cutSize: 5)
                            .strokeBorder(Color.jarvisBlue.opacity(0.2), lineWidth: 0.5)
                    }
            }
        }
    }

    // MARK: - Loading Indicator

    private var loadingIndicator: some View {
        VStack(spacing: 8) {
            ProgressView()
                .tint(.jarvisBlue)

            if totalToGeocode > 0 {
                Text("GEOCODING \(geocodedCount)/\(totalToGeocode)")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .tracking(1.5)
                    .foregroundColor(.jarvisBlue.opacity(0.6))
            } else {
                Text("LOADING CONTACTS")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .tracking(1.5)
                    .foregroundColor(.jarvisBlue.opacity(0.6))
            }
        }
        .padding(16)
        .glassBackground(opacity: 0.7, cutSize: 8)
    }

    // MARK: - Error Banner

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 12))
                .foregroundColor(.jarvisError)

            Text(message.uppercased())
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .tracking(1)
                .foregroundColor(.jarvisError.opacity(0.8))
        }
        .padding(12)
        .glassBackground(opacity: 0.7, cutSize: 6)
    }

    // MARK: - Search

    private func search() async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            searchResults = []
            return
        }

        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = query

        // Use default region for search context
        request.region = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 40.29, longitude: -111.69),
            span: MKCoordinateSpan(latitudeDelta: 5.0, longitudeDelta: 5.0)
        )

        do {
            let response = try await MKLocalSearch(request: request).start()
            searchResults = response.mapItems

            // Center on first result
            if let first = response.mapItems.first,
               let coord = first.placemark.location?.coordinate {
                withAnimation(.easeInOut(duration: 0.5)) {
                    position = .region(MKCoordinateRegion(
                        center: coord,
                        span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                    ))
                }
            }
        } catch {
            // Search failed silently — map stays as is
        }
    }

    // MARK: - Load Contacts

    private func loadContacts() async {
        isLoading = true
        errorMessage = nil

        do {
            let apiContacts: [ContactAPIResponse] = try await APIClient.shared.request(
                JARVISConfig.Contacts.list
            )

            // Filter contacts that have address info for geocoding
            let geocodable = apiContacts.filter { $0.fullAddress != nil }
            totalToGeocode = geocodable.count
            geocodedCount = 0

            var mapped: [AtlasContact] = []
            let geocoder = CLGeocoder()

            for apiContact in geocodable {
                guard let address = apiContact.fullAddress else { continue }

                // Geocode the address
                do {
                    let placemarks = try await geocoder.geocodeAddressString(address)
                    if let location = placemarks.first?.location {
                        let contact = AtlasContact(
                            id: apiContact.id,
                            name: apiContact.fullName,
                            phone: apiContact.phone,
                            email: apiContact.email,
                            address: apiContact.fullAddress,
                            company: apiContact.company,
                            city: apiContact.city,
                            state: apiContact.state,
                            coordinate: location.coordinate,
                            photoBase64: apiContact.photo,
                            photoContentType: apiContact.photo_content_type
                        )
                        mapped.append(contact)
                    }
                } catch {
                    // Skip contacts that fail to geocode
                }

                geocodedCount += 1

                // Brief delay to respect geocoding rate limits
                if geocodedCount < totalToGeocode {
                    try? await Task.sleep(for: .milliseconds(150))
                }
            }

            contacts = mapped
            isLoading = false

            // Fit map to show all contacts
            if !mapped.isEmpty {
                fitMapToContacts(mapped)
            }
        } catch {
            isLoading = false
            errorMessage = "Failed to load contacts"
        }
    }

    // MARK: - Fit Map

    private func fitMapToContacts(_ contacts: [AtlasContact]) {
        guard !contacts.isEmpty else { return }

        if contacts.count == 1 {
            withAnimation(.easeInOut(duration: 0.5)) {
                position = .region(MKCoordinateRegion(
                    center: contacts[0].coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.1, longitudeDelta: 0.1)
                ))
            }
            return
        }

        var minLat = contacts[0].coordinate.latitude
        var maxLat = contacts[0].coordinate.latitude
        var minLng = contacts[0].coordinate.longitude
        var maxLng = contacts[0].coordinate.longitude

        for contact in contacts {
            minLat = min(minLat, contact.coordinate.latitude)
            maxLat = max(maxLat, contact.coordinate.latitude)
            minLng = min(minLng, contact.coordinate.longitude)
            maxLng = max(maxLng, contact.coordinate.longitude)
        }

        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLng + maxLng) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: (maxLat - minLat) * 1.4 + 0.02,
            longitudeDelta: (maxLng - minLng) * 1.4 + 0.02
        )

        withAnimation(.easeInOut(duration: 0.5)) {
            position = .region(MKCoordinateRegion(center: center, span: span))
        }
    }
}
