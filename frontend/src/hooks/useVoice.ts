import { useState, useCallback, useRef, useEffect } from 'react';
import { useUIStore } from '@/stores/uiStore';
import { api } from '@/services/api';

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcription, setTranscription] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const { setIsListening, setIsSpeaking, setJarvisActivity } = useUIStore();

  const analyzeAudio = useCallback(() => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    const sum = dataArray.reduce((a, b) => a + b, 0);
    const average = sum / dataArray.length;
    const normalizedLevel = Math.min(average / 128, 1);

    setAudioLevel(normalizedLevel);
    setJarvisActivity(0.3 + normalizedLevel * 0.5);

    animFrameRef.current = requestAnimationFrame(analyzeAudio);
  }, [setJarvisActivity]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });

      streamRef.current = stream;
      chunksRef.current = [];

      audioContextRef.current = new AudioContext();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      source.connect(analyserRef.current);

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await transcribeAudio(audioBlob);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(100);
      setIsRecording(true);
      setIsListening(true);
      analyzeAudio();
    } catch (err) {
      console.error('Failed to start recording:', err);
    }
  }, [setIsListening, analyzeAudio]);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.onstop = () => {
          const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
          resolve(audioBlob);
        };
        mediaRecorderRef.current.stop();
      } else {
        resolve(null);
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }

      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }

      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }

      setIsRecording(false);
      setIsListening(false);
      setAudioLevel(0);
    });
  }, [setIsListening]);

  const transcribeAudio = useCallback(async (audioBlob: Blob) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      const response = await api.postFormData<{ text: string }>('/voice/transcribe', formData);
      setTranscription(response.text);
      return response.text;
    } catch (err) {
      console.error('Transcription failed:', err);
      setTranscription('');
      return '';
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  const playAudio = useCallback(
    async (source: string | Blob) => {
      setIsSpeaking(true);
      setJarvisActivity(0.8);

      try {
        const url = source instanceof Blob ? URL.createObjectURL(source) : source;
        const audio = new Audio(url);

        const playbackContext = new AudioContext();
        const playbackSource = playbackContext.createMediaElementSource(audio);
        const playbackAnalyser = playbackContext.createAnalyser();
        playbackAnalyser.fftSize = 256;
        playbackSource.connect(playbackAnalyser);
        playbackAnalyser.connect(playbackContext.destination);

        const analyzePlayback = () => {
          const dataArray = new Uint8Array(playbackAnalyser.frequencyBinCount);
          playbackAnalyser.getByteFrequencyData(dataArray);
          const sum = dataArray.reduce((a, b) => a + b, 0);
          const average = sum / dataArray.length;
          setJarvisActivity(0.4 + (average / 128) * 0.6);

          if (!audio.paused && !audio.ended) {
            requestAnimationFrame(analyzePlayback);
          }
        };

        audio.onplay = () => analyzePlayback();

        audio.onended = () => {
          setIsSpeaking(false);
          setJarvisActivity(0.1);
          playbackContext.close();
          if (source instanceof Blob) {
            URL.revokeObjectURL(url);
          }
        };

        audio.onerror = () => {
          setIsSpeaking(false);
          setJarvisActivity(0);
          playbackContext.close();
        };

        await audio.play();
      } catch (err) {
        console.error('Audio playback failed:', err);
        setIsSpeaking(false);
        setJarvisActivity(0);
      }
    },
    [setIsSpeaking, setJarvisActivity]
  );

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, []);

  return {
    isRecording,
    transcription,
    isTranscribing,
    audioLevel,
    startRecording,
    stopRecording,
    transcribeAudio,
    playAudio,
  };
}
