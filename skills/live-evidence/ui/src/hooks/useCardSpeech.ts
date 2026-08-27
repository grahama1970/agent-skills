import { useEffect, useCallback, useRef } from "react";

interface CardData {
  title: string;
  body: string;
}

interface UseCardAudioOptions {
  enabled?: boolean;
  speechRate?: number; // 0.1 to 10 (1.3x for accelerated interview pacing)
  pitch?: number;
  readBody?: boolean;
}

export function useCardSpeech(
  activeCard: CardData | undefined,
  options: UseCardAudioOptions = {},
) {
  const { enabled = true, speechRate = 1.3, pitch = 1.0, readBody = false } = options;
  const synthRef = useRef<SpeechSynthesis | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      synthRef.current = window.speechSynthesis;
    }
  }, []);

  const announce = useCallback(
    (card: CardData) => {
      if (!enabled || !synthRef.current) return;
      synthRef.current.cancel();
      const script = readBody ? `${card.title}. ${card.body}` : card.title;
      const utterance = new SpeechSynthesisUtterance(script);
      utterance.rate = speechRate;
      utterance.pitch = pitch;
      const voices = synthRef.current.getVoices();
      const englishVoice =
        voices.find(
          (v) => v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Enhanced")),
        ) || voices.find((v) => v.lang.startsWith("en"));
      if (englishVoice) utterance.voice = englishVoice;
      synthRef.current.speak(utterance);
    },
    [enabled, speechRate, pitch, readBody],
  );

  useEffect(() => {
    if (activeCard) announce(activeCard);
    return () => {
      synthRef.current?.cancel();
    };
  }, [activeCard, announce]);
}
