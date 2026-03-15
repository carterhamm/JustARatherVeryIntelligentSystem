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

    /// Search for a song and play it immediately via Apple Music
    func playSong(query: String) async throws -> String {
        guard isAuthorized else {
            return "Apple Music not authorized. Please connect in Settings."
        }

        let songs = try await search(query: query)
        guard let song = songs.first else {
            return "No results found for '\(query)' on Apple Music."
        }

        let player = ApplicationMusicPlayer.shared
        player.queue = [song]
        try await player.play()

        logger.info("Now playing: \(song.title) by \(song.artistName)")
        return "Now playing: \(song.title) by \(song.artistName)"
    }

    /// Play/pause/skip via simple command
    func handleCommand(_ command: String) async -> String {
        switch command.lowercased() {
        case "pause", "stop":
            pause()
            return "Music paused."
        case "play", "resume":
            play()
            return "Resuming playback."
        case "next", "skip":
            next()
            return "Skipped to next track."
        case "previous", "back":
            previous()
            return "Back to previous track."
        default:
            if command.lowercased().starts(with: "play ") {
                let query = String(command.dropFirst(5))
                return (try? await playSong(query: query)) ?? "Couldn't play that song."
            }
            return "Unknown music command."
        }
    }
}
