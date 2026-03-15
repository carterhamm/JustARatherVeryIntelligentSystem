import MediaPlayer
import MusicKit
import os

actor MusicService {
    static let shared = MusicService()

    private let logger = Logger(subsystem: "dev.jarvis.malibupoint", category: "Music")

    func requestAccess() async -> Bool {
        let status = await MusicAuthorization.request()
        logger.info("Music access: \(String(describing: status))")
        return status == .authorized
    }

    var isAuthorized: Bool {
        MusicAuthorization.currentStatus == .authorized
    }

    var authorizationStatus: MusicAuthorization.Status {
        MusicAuthorization.currentStatus
    }

    func nowPlaying() -> (title: String, artist: String)? {
        let player = MPMusicPlayerController.systemMusicPlayer
        guard let item = player.nowPlayingItem else { return nil }
        return (title: item.title ?? "Unknown", artist: item.artist ?? "Unknown")
    }

    func play() {
        MPMusicPlayerController.systemMusicPlayer.play()
        logger.debug("Playback: play")
    }

    func pause() {
        MPMusicPlayerController.systemMusicPlayer.pause()
        logger.debug("Playback: pause")
    }

    func next() {
        MPMusicPlayerController.systemMusicPlayer.skipToNextItem()
        logger.debug("Playback: next")
    }

    func previous() {
        MPMusicPlayerController.systemMusicPlayer.skipToPreviousItem()
        logger.debug("Playback: previous")
    }

    func search(query: String) async throws -> [MusicItemCollection<Song>.Element] {
        var request = MusicCatalogSearchRequest(term: query, types: [Song.self])
        request.limit = 10
        let response = try await request.response()
        logger.info("Music search '\(query)': \(response.songs.count) results")
        return Array(response.songs)
    }
}
