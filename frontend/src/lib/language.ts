export const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", hi: "Hindi", bn: "Bengali", te: "Telugu", mr: "Marathi", ta: "Tamil", ur: "Urdu",
  gu: "Gujarati", kn: "Kannada", ml: "Malayalam", or: "Odia", pa: "Punjabi", as: "Assamese",
  mai: "Maithili", sa: "Sanskrit", ks: "Kashmiri", ne: "Nepali", sd: "Sindhi", kok: "Konkani",
  doi: "Dogri", mni: "Manipuri", sat: "Santali", brx: "Bodo", fr: "French", de: "German", es: "Spanish",
};

export function languageName(code: string | null | undefined): string | null {
  if (!code) return null;
  return LANGUAGE_NAMES[code] ?? code;
}

/** The same question in several scripts: the empty-state hero. */
export const HERO_LINES: { lang: string; text: string; width: number }[] = [
  { lang: "hi", text: "यह दस्तावेज़ क्या कहता है?", width: 112 },
  { lang: "ta", text: "இந்த ஆவணம் என்ன சொல்கிறது?", width: 88 },
  { lang: "en", text: "What does this document say?", width: 100 },
  { lang: "bn", text: "এই নথিতে কী বলা আছে?", width: 120 },
  { lang: "te", text: "ఈ పత్రం ఏమి చెబుతోంది?", width: 95 },
  { lang: "kn", text: "ಈ ದಾಖಲೆ ಏನು ಹೇಳುತ್ತದೆ?", width: 105 },
  { lang: "ml", text: "ഈ രേഖ എന്താണ് പറയുന്നത്?", width: 82 },
  { lang: "gu", text: "આ દસ્તાવેજ શું કહે છે?", width: 115 },
];
