// Adhikar i18n — single source of truth for the language switch.
// Layer 1: shipped bundles (offline, instant). Sarvam's 11 = 10 Indian + English.
// NOTE: Odia is od-IN (Sarvam convention), not or-IN. All 11 are LTR.
(function () {
  const LANGUAGES = [
    { code: 'en-IN', label: 'English',   native: 'English' },
    { code: 'hi-IN', label: 'Hindi',     native: 'हिन्दी' },
    { code: 'mr-IN', label: 'Marathi',   native: 'मराठी' },
    { code: 'bn-IN', label: 'Bengali',   native: 'বাংলা' },
    { code: 'gu-IN', label: 'Gujarati',  native: 'ગુજરાતી' },
    { code: 'kn-IN', label: 'Kannada',   native: 'ಕನ್ನಡ' },
    { code: 'ml-IN', label: 'Malayalam', native: 'മലയാളം' },
    { code: 'od-IN', label: 'Odia',      native: 'ଓଡ଼ିଆ' },
    { code: 'pa-IN', label: 'Punjabi',   native: 'ਪੰਜਾਬੀ' },
    { code: 'ta-IN', label: 'Tamil',     native: 'தமிழ்' },
    { code: 'te-IN', label: 'Telugu',    native: 'తెలుగు' }
  ];
  const DEFAULT_LOCALE = 'en-IN';

  // en-IN is the authored source of truth. Other bundles are bootstrap
  // translations pending native-speaker review (rights/disclaimer strings
  // especially) — same rule as the playbook: don't treat as final legal copy.
  const STRINGS = {
    'en-IN': {
      'nav.what': 'What it does', 'nav.how': 'How it works', 'nav.scan': 'Scan a site', 'nav.act': 'The DPDP Act', 'nav.guide': 'Permissions guide', 'nav.add': 'Add to Chrome',
      'hero.kicker': 'Adhikar \u00b7 Your data rights companion', 'hero.l1': 'Know what they', 'hero.know': 'know', 'hero.l3': 'about you.',
      'hero.sub': 'Your data has a story. Read it.', 'hero.cta2': 'See how it works',
      'strip.h': 'Try it now. Scan any site.', 'strip.sub': "A live read of a site's privacy story, run in your browser. Nothing is stored.",
      'scan.badge': 'Live scanner', 'scan.h1': 'Scan a site. Read its story.',
      'scan.sub': 'Paste a website address or its privacy policy text. The scan runs live, in your browser, and keeps nothing.',
      'scan.btn': 'Scan', 'scan.paste': 'Or paste the policy text instead', 'scan.hide': 'Hide the paste box', 'scan.analyse': 'Analyse this text',
      'scan.fetching': 'Reaching the site and its policy pages\u2026', 'scan.reading': 'Reading the real text against the DPDP Act and Rules\u2026', 'scan.translating': 'Translating into your language\u2026',
      'result.title': 'Scan result', 'tab.you': 'Your data risk', 'tab.site': 'DPDP compliance',
      'result.collects': 'What it says it collects', 'result.baseline': 'More than it needs?', 'result.guidance': 'Guidance, not law', 'result.rights': 'Your rights here',
      'result.disclaimer': 'This is guidance, not legal advice. For compliance decisions, consult a qualified lawyer.',
      'result.stored': 'This scan read the text provided and kept nothing. No report was stored.',
      'result.translated': 'Machine-translated from the English source. Quoted clauses and citations stay in the original.',
      'handoff.chip': "Couldn't reach the site", 'handoff.title': "We won't guess."
    },
    'hi-IN': {
      'nav.what': 'यह क्या करता है', 'nav.how': 'यह कैसे काम करता है', 'nav.scan': 'साइट स्कैन करें', 'nav.act': 'DPDP क़ानून', 'nav.guide': 'अनुमति गाइड', 'nav.add': 'Chrome में जोड़ें',
      'hero.kicker': 'अधिकार \u00b7 आपका डेटा-अधिकार साथी', 'hero.l1': 'जानिए, वे', 'hero.know': 'क्या जानते हैं', 'hero.l3': 'आपके बारे में।',
      'hero.sub': 'आपके डेटा की एक कहानी है। उसे पढ़िए।', 'hero.cta2': 'देखें यह कैसे काम करता है',
      'strip.h': 'अभी आज़माएँ। कोई भी साइट स्कैन करें।', 'strip.sub': 'साइट की प्राइवेसी कहानी की लाइव पड़ताल, आपके ब्राउज़र में। कुछ भी सहेजा नहीं जाता।',
      'scan.badge': 'लाइव स्कैनर', 'scan.h1': 'साइट स्कैन करें। उसकी कहानी पढ़ें।',
      'scan.sub': 'वेबसाइट का पता या उसकी प्राइवेसी पॉलिसी का टेक्स्ट चिपकाएँ। स्कैन आपके ब्राउज़र में लाइव चलता है और कुछ भी सहेजता नहीं।',
      'scan.btn': 'स्कैन करें', 'scan.paste': 'या पॉलिसी का टेक्स्ट चिपकाएँ', 'scan.hide': 'पेस्ट बॉक्स छिपाएँ', 'scan.analyse': 'इस टेक्स्ट का विश्लेषण करें',
      'scan.fetching': 'साइट और उसके पॉलिसी पेज खोले जा रहे हैं\u2026', 'scan.reading': 'असली टेक्स्ट को DPDP क़ानून से मिलाकर पढ़ा जा रहा है\u2026', 'scan.translating': 'आपकी भाषा में अनुवाद हो रहा है\u2026',
      'result.title': 'स्कैन नतीजा', 'tab.you': 'आपका डेटा जोखिम', 'tab.site': 'DPDP अनुपालन',
      'result.collects': 'यह क्या इकट्ठा करने की बात कहता है', 'result.baseline': 'ज़रूरत से ज़्यादा?', 'result.guidance': 'मार्गदर्शन, क़ानून नहीं', 'result.rights': 'यहाँ आपके अधिकार',
      'result.disclaimer': 'यह मार्गदर्शन है, क़ानूनी सलाह नहीं। अनुपालन के फ़ैसलों के लिए योग्य वकील से सलाह लें।',
      'result.stored': 'इस स्कैन ने दिया गया टेक्स्ट पढ़ा और कुछ नहीं रखा। कोई रिपोर्ट सहेजी नहीं गई।',
      'result.translated': 'अंग्रेज़ी स्रोत से मशीन-अनुवादित। उद्धृत अंश और संदर्भ मूल भाषा में ही रहते हैं।',
      'handoff.chip': 'साइट तक नहीं पहुँच सके', 'handoff.title': 'हम अंदाज़ा नहीं लगाएँगे।'
    },
    'mr-IN': {
      'nav.what': 'हे काय करते', 'nav.how': 'हे कसे काम करते', 'nav.scan': 'साइट स्कॅन करा', 'nav.act': 'DPDP कायदा', 'nav.guide': 'परवानगी मार्गदर्शक', 'nav.add': 'Chrome मध्ये जोडा',
      'hero.kicker': 'अधिकार \u00b7 तुमचा डेटा-हक्क साथीदार', 'hero.l1': 'जाणून घ्या, ते', 'hero.know': 'काय जाणतात', 'hero.l3': 'तुमच्याबद्दल.',
      'hero.sub': 'तुमच्या डेटाची एक गोष्ट आहे. ती वाचा.', 'hero.cta2': 'हे कसे काम करते ते पहा',
      'strip.h': 'आत्ताच करून पहा. कोणतीही साइट स्कॅन करा.', 'strip.sub': 'साइटच्या प्रायव्हसी गोष्टीचे थेट वाचन, तुमच्या ब्राउझरमध्ये. काहीही साठवले जात नाही.',
      'scan.badge': 'लाइव्ह स्कॅनर', 'scan.h1': 'साइट स्कॅन करा. तिची गोष्ट वाचा.',
      'scan.sub': 'वेबसाइटचा पत्ता किंवा तिच्या प्रायव्हसी पॉलिसीचा मजकूर चिकटवा. स्कॅन तुमच्या ब्राउझरमध्ये थेट चालते आणि काहीही साठवत नाही.',
      'scan.btn': 'स्कॅन करा', 'scan.paste': 'किंवा पॉलिसीचा मजकूर चिकटवा', 'scan.hide': 'पेस्ट बॉक्स लपवा', 'scan.analyse': 'या मजकुराचे विश्लेषण करा',
      'scan.fetching': 'साइट आणि तिची पॉलिसी पाने उघडत आहोत\u2026', 'scan.reading': 'खरा मजकूर DPDP कायद्याशी ताडून वाचत आहोत\u2026', 'scan.translating': 'तुमच्या भाषेत अनुवाद होत आहे\u2026',
      'result.title': 'स्कॅन निकाल', 'tab.you': 'तुमचा डेटा धोका', 'tab.site': 'DPDP अनुपालन',
      'result.collects': 'हे काय गोळा करते असे म्हणते', 'result.baseline': 'गरजेपेक्षा जास्त?', 'result.guidance': 'मार्गदर्शन, कायदा नव्हे', 'result.rights': 'इथे तुमचे हक्क',
      'result.disclaimer': 'हे मार्गदर्शन आहे, कायदेशीर सल्ला नाही. अनुपालनाच्या निर्णयांसाठी पात्र वकिलाचा सल्ला घ्या.',
      'result.stored': 'या स्कॅनने दिलेला मजकूर वाचला आणि काहीही ठेवले नाही. कोणताही अहवाल साठवला नाही.',
      'result.translated': 'इंग्रजी स्रोतावरून मशीन-अनुवादित. उद्धृत कलमे व संदर्भ मूळ भाषेतच राहतात.',
      'handoff.chip': 'साइटपर्यंत पोहोचता आले नाही', 'handoff.title': 'आम्ही अंदाज बांधणार नाही.'
    },
    'bn-IN': {
      'nav.what': 'এটি কী করে', 'nav.how': 'এটি কীভাবে কাজ করে', 'nav.scan': 'সাইট স্ক্যান করুন', 'nav.act': 'DPDP আইন', 'nav.guide': 'অনুমতি নির্দেশিকা', 'nav.add': 'Chrome-এ যোগ করুন',
      'hero.kicker': 'অধিকার \u00b7 আপনার ডেটা-অধিকারের সঙ্গী', 'hero.l1': 'জানুন, তারা', 'hero.know': 'কী জানে', 'hero.l3': 'আপনার সম্পর্কে।',
      'hero.sub': 'আপনার ডেটার একটা গল্প আছে। সেটা পড়ুন।', 'hero.cta2': 'কীভাবে কাজ করে দেখুন',
      'strip.h': 'এখনই দেখুন। যেকোনো সাইট স্ক্যান করুন।', 'strip.sub': 'সাইটের প্রাইভেসি গল্পের লাইভ পাঠ, আপনার ব্রাউজারে। কিছুই সংরক্ষণ হয় না।',
      'scan.badge': 'লাইভ স্ক্যানার', 'scan.h1': 'সাইট স্ক্যান করুন। তার গল্প পড়ুন।',
      'scan.sub': 'ওয়েবসাইটের ঠিকানা বা তার প্রাইভেসি পলিসির লেখা পেস্ট করুন। স্ক্যান আপনার ব্রাউজারে লাইভ চলে, কিছুই রাখে না।',
      'scan.btn': 'স্ক্যান', 'scan.paste': 'বা পলিসির লেখা পেস্ট করুন', 'scan.hide': 'পেস্ট বক্স লুকান', 'scan.analyse': 'এই লেখা বিশ্লেষণ করুন',
      'scan.fetching': 'সাইট ও তার পলিসি পাতা খোলা হচ্ছে\u2026', 'scan.reading': 'আসল লেখা DPDP আইনের সঙ্গে মিলিয়ে পড়া হচ্ছে\u2026', 'scan.translating': 'আপনার ভাষায় অনুবাদ হচ্ছে\u2026',
      'result.title': 'স্ক্যান ফলাফল', 'tab.you': 'আপনার ডেটা ঝুঁকি', 'tab.site': 'DPDP সম্মতি',
      'result.collects': 'এটি কী সংগ্রহ করে বলে জানায়', 'result.baseline': 'প্রয়োজনের চেয়ে বেশি?', 'result.guidance': 'নির্দেশনা, আইন নয়', 'result.rights': 'এখানে আপনার অধিকার',
      'result.disclaimer': 'এটি নির্দেশনা, আইনি পরামর্শ নয়। সম্মতির সিদ্ধান্তের জন্য যোগ্য আইনজীবীর পরামর্শ নিন।',
      'result.stored': 'এই স্ক্যান দেওয়া লেখা পড়েছে, কিছুই রাখেনি। কোনো রিপোর্ট সংরক্ষণ হয়নি।',
      'result.translated': 'ইংরেজি উৎস থেকে যন্ত্র-অনূদিত। উদ্ধৃত ধারা ও সূত্র মূল ভাষাতেই থাকে।',
      'handoff.chip': 'সাইটে পৌঁছানো যায়নি', 'handoff.title': 'আমরা অনুমান করব না।'
    },
    'gu-IN': {
      'nav.what': 'આ શું કરે છે', 'nav.how': 'આ કેવી રીતે કામ કરે છે', 'nav.scan': 'સાઇટ સ્કૅન કરો', 'nav.act': 'DPDP કાયદો', 'nav.guide': 'પરવાનગી માર્ગદર્શિકા', 'nav.add': 'Chrome માં ઉમેરો',
      'hero.kicker': 'અધિકાર \u00b7 તમારો ડેટા-અધિકાર સાથી', 'hero.l1': 'જાણો, તેઓ', 'hero.know': 'શું જાણે છે', 'hero.l3': 'તમારા વિશે.',
      'hero.sub': 'તમારા ડેટાની એક વાર્તા છે. તે વાંચો.', 'hero.cta2': 'આ કેવી રીતે કામ કરે છે તે જુઓ',
      'strip.h': 'હમણાં જ અજમાવો. કોઈપણ સાઇટ સ્કૅન કરો.', 'strip.sub': 'સાઇટની પ્રાઇવસી વાર્તાનું લાઇવ વાંચન, તમારા બ્રાઉઝરમાં. કંઈ સંગ્રહાતું નથી.',
      'scan.badge': 'લાઇવ સ્કૅનર', 'scan.h1': 'સાઇટ સ્કૅન કરો. તેની વાર્તા વાંચો.',
      'scan.sub': 'વેબસાઇટનું સરનામું અથવા તેની પ્રાઇવસી પોલિસીનો ટેક્સ્ટ પેસ્ટ કરો. સ્કૅન તમારા બ્રાઉઝરમાં લાઇવ ચાલે છે અને કંઈ રાખતું નથી.',
      'scan.btn': 'સ્કૅન કરો', 'scan.paste': 'અથવા પોલિસીનો ટેક્સ્ટ પેસ્ટ કરો', 'scan.hide': 'પેસ્ટ બોક્સ છુપાવો', 'scan.analyse': 'આ ટેક્સ્ટનું વિશ્લેષણ કરો',
      'scan.fetching': 'સાઇટ અને તેનાં પોલિસી પાનાં ખોલી રહ્યા છીએ\u2026', 'scan.reading': 'સાચો ટેક્સ્ટ DPDP કાયદા સાથે સરખાવી વાંચી રહ્યા છીએ\u2026', 'scan.translating': 'તમારી ભાષામાં અનુવાદ થઈ રહ્યો છે\u2026',
      'result.title': 'સ્કૅન પરિણામ', 'tab.you': 'તમારું ડેટા જોખમ', 'tab.site': 'DPDP અનુપાલન',
      'result.collects': 'આ શું એકત્ર કરે છે એમ કહે છે', 'result.baseline': 'જરૂર કરતાં વધુ?', 'result.guidance': 'માર્ગદર્શન, કાયદો નહીં', 'result.rights': 'અહીં તમારા અધિકારો',
      'result.disclaimer': 'આ માર્ગદર્શન છે, કાનૂની સલાહ નથી. અનુપાલનના નિર્ણયો માટે લાયક વકીલની સલાહ લો.',
      'result.stored': 'આ સ્કૅને આપેલો ટેક્સ્ટ વાંચ્યો અને કંઈ રાખ્યું નહીં. કોઈ રિપોર્ટ સંગ્રહાયો નથી.',
      'result.translated': 'અંગ્રેજી સ્રોતમાંથી મશીન-અનુવાદિત. ટાંકેલી કલમો અને સંદર્ભો મૂળ ભાષામાં જ રહે છે.',
      'handoff.chip': 'સાઇટ સુધી પહોંચી શકાયું નહીં', 'handoff.title': 'અમે અનુમાન નહીં કરીએ.'
    },
    'kn-IN': {
      'nav.what': 'ಇದು ಏನು ಮಾಡುತ್ತದೆ', 'nav.how': 'ಇದು ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ', 'nav.scan': 'ಸೈಟ್ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ', 'nav.act': 'DPDP ಕಾಯ್ದೆ', 'nav.guide': 'ಅನುಮತಿ ಮಾರ್ಗದರ್ಶಿ', 'nav.add': 'Chrome ಗೆ ಸೇರಿಸಿ',
      'hero.kicker': 'ಅಧಿಕಾರ್ \u00b7 ನಿಮ್ಮ ಡೇಟಾ-ಹಕ್ಕುಗಳ ಸಂಗಾತಿ', 'hero.l1': 'ತಿಳಿಯಿರಿ, ಅವರು', 'hero.know': 'ಏನು ಬಲ್ಲರು', 'hero.l3': 'ನಿಮ್ಮ ಬಗ್ಗೆ.',
      'hero.sub': 'ನಿಮ್ಮ ಡೇಟಾಗೆ ಒಂದು ಕಥೆ ಇದೆ. ಅದನ್ನು ಓದಿ.', 'hero.cta2': 'ಇದು ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ ನೋಡಿ',
      'strip.h': 'ಈಗಲೇ ಪ್ರಯತ್ನಿಸಿ. ಯಾವುದೇ ಸೈಟ್ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ.', 'strip.sub': 'ಸೈಟ್\u200cನ ಪ್ರೈವಸಿ ಕಥೆಯ ಲೈವ್ ಓದು, ನಿಮ್ಮ ಬ್ರೌಸರ್\u200cನಲ್ಲಿ. ಏನೂ ಸಂಗ್ರಹವಾಗುವುದಿಲ್ಲ.',
      'scan.badge': 'ಲೈವ್ ಸ್ಕ್ಯಾನರ್', 'scan.h1': 'ಸೈಟ್ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ. ಅದರ ಕಥೆ ಓದಿ.',
      'scan.sub': 'ವೆಬ್\u200cಸೈಟ್ ವಿಳಾಸ ಅಥವಾ ಅದರ ಪ್ರೈವಸಿ ಪಾಲಿಸಿ ಪಠ್ಯವನ್ನು ಅಂಟಿಸಿ. ಸ್ಕ್ಯಾನ್ ನಿಮ್ಮ ಬ್ರೌಸರ್\u200cನಲ್ಲೇ ಲೈವ್ ನಡೆಯುತ್ತದೆ, ಏನನ್ನೂ ಇಟ್ಟುಕೊಳ್ಳುವುದಿಲ್ಲ.',
      'scan.btn': 'ಸ್ಕ್ಯಾನ್', 'scan.paste': 'ಅಥವಾ ಪಾಲಿಸಿ ಪಠ್ಯವನ್ನು ಅಂಟಿಸಿ', 'scan.hide': 'ಪೇಸ್ಟ್ ಬಾಕ್ಸ್ ಮರೆಮಾಡಿ', 'scan.analyse': 'ಈ ಪಠ್ಯವನ್ನು ವಿಶ್ಲೇಷಿಸಿ',
      'scan.fetching': 'ಸೈಟ್ ಮತ್ತು ಅದರ ಪಾಲಿಸಿ ಪುಟಗಳನ್ನು ತಲುಪುತ್ತಿದ್ದೇವೆ\u2026', 'scan.reading': 'ನಿಜವಾದ ಪಠ್ಯವನ್ನು DPDP ಕಾಯ್ದೆಯೊಂದಿಗೆ ಹೋಲಿಸಿ ಓದುತ್ತಿದ್ದೇವೆ\u2026', 'scan.translating': 'ನಿಮ್ಮ ಭಾಷೆಗೆ ಅನುವಾದಿಸಲಾಗುತ್ತಿದೆ\u2026',
      'result.title': 'ಸ್ಕ್ಯಾನ್ ಫಲಿತಾಂಶ', 'tab.you': 'ನಿಮ್ಮ ಡೇಟಾ ಅಪಾಯ', 'tab.site': 'DPDP ಅನುಸರಣೆ',
      'result.collects': 'ಇದು ಏನು ಸಂಗ್ರಹಿಸುತ್ತದೆ ಎಂದು ಹೇಳುತ್ತದೆ', 'result.baseline': 'ಅಗತ್ಯಕ್ಕಿಂತ ಹೆಚ್ಚೇ?', 'result.guidance': 'ಮಾರ್ಗದರ್ಶನ, ಕಾನೂನಲ್ಲ', 'result.rights': 'ಇಲ್ಲಿ ನಿಮ್ಮ ಹಕ್ಕುಗಳು',
      'result.disclaimer': 'ಇದು ಮಾರ್ಗದರ್ಶನ, ಕಾನೂನು ಸಲಹೆಯಲ್ಲ. ಅನುಸರಣೆ ನಿರ್ಧಾರಗಳಿಗೆ ಅರ್ಹ ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.',
      'result.stored': 'ಈ ಸ್ಕ್ಯಾನ್ ನೀಡಿದ ಪಠ್ಯವನ್ನು ಓದಿತು, ಏನನ್ನೂ ಇಟ್ಟುಕೊಳ್ಳಲಿಲ್ಲ. ಯಾವುದೇ ವರದಿ ಸಂಗ್ರಹವಾಗಿಲ್ಲ.',
      'result.translated': 'ಇಂಗ್ಲಿಷ್ ಮೂಲದಿಂದ ಯಂತ್ರ-ಅನುವಾದ. ಉಲ್ಲೇಖಿತ ಷರತ್ತುಗಳು ಮೂಲ ಭಾಷೆಯಲ್ಲೇ ಇರುತ್ತವೆ.',
      'handoff.chip': 'ಸೈಟ್ ತಲುಪಲಾಗಲಿಲ್ಲ', 'handoff.title': 'ನಾವು ಊಹಿಸುವುದಿಲ್ಲ.'
    },
    'ml-IN': {
      'nav.what': 'ഇത് എന്ത് ചെയ്യുന്നു', 'nav.how': 'ഇത് എങ്ങനെ പ്രവർത്തിക്കുന്നു', 'nav.scan': 'സൈറ്റ് സ്കാൻ ചെയ്യുക', 'nav.act': 'DPDP നിയമം', 'nav.guide': 'അനുമതി ഗൈഡ്', 'nav.add': 'Chrome-ൽ ചേർക്കുക',
      'hero.kicker': 'അധികാർ \u00b7 നിങ്ങളുടെ ഡാറ്റാ-അവകാശ കൂട്ടാളി', 'hero.l1': 'അറിയൂ, അവർ', 'hero.know': 'എന്തറിയുന്നു', 'hero.l3': 'നിങ്ങളെക്കുറിച്ച്.',
      'hero.sub': 'നിങ്ങളുടെ ഡാറ്റയ്ക്ക് ഒരു കഥയുണ്ട്. അത് വായിക്കൂ.', 'hero.cta2': 'ഇത് എങ്ങനെ പ്രവർത്തിക്കുന്നു കാണുക',
      'strip.h': 'ഇപ്പോൾ തന്നെ പരീക്ഷിക്കൂ. ഏത് സൈറ്റും സ്കാൻ ചെയ്യൂ.', 'strip.sub': 'സൈറ്റിന്റെ പ്രൈവസി കഥയുടെ തത്സമയ വായന, നിങ്ങളുടെ ബ്രൗസറിൽ. ഒന്നും സൂക്ഷിക്കുന്നില്ല.',
      'scan.badge': 'ലൈവ് സ്കാനർ', 'scan.h1': 'സൈറ്റ് സ്കാൻ ചെയ്യൂ. അതിന്റെ കഥ വായിക്കൂ.',
      'scan.sub': 'വെബ്സൈറ്റ് വിലാസമോ അതിന്റെ പ്രൈവസി പോളിസി ടെക്സ്റ്റോ പേസ്റ്റ് ചെയ്യുക. സ്കാൻ നിങ്ങളുടെ ബ്രൗസറിൽ തത്സമയം നടക്കുന്നു, ഒന്നും സൂക്ഷിക്കുന്നില്ല.',
      'scan.btn': 'സ്കാൻ', 'scan.paste': 'അല്ലെങ്കിൽ പോളിസി ടെക്സ്റ്റ് പേസ്റ്റ് ചെയ്യുക', 'scan.hide': 'പേസ്റ്റ് ബോക്സ് മറയ്ക്കുക', 'scan.analyse': 'ഈ ടെക്സ്റ്റ് വിശകലനം ചെയ്യുക',
      'scan.fetching': 'സൈറ്റും അതിന്റെ പോളിസി പേജുകളും തുറക്കുന്നു\u2026', 'scan.reading': 'യഥാർത്ഥ ടെക്സ്റ്റ് DPDP നിയമവുമായി ഒത്തുനോക്കി വായിക്കുന്നു\u2026', 'scan.translating': 'നിങ്ങളുടെ ഭാഷയിലേക്ക് വിവർത്തനം ചെയ്യുന്നു\u2026',
      'result.title': 'സ്കാൻ ഫലം', 'tab.you': 'നിങ്ങളുടെ ഡാറ്റാ അപകടസാധ്യത', 'tab.site': 'DPDP അനുസരണം',
      'result.collects': 'ഇത് എന്ത് ശേഖരിക്കുന്നു എന്ന് പറയുന്നു', 'result.baseline': 'ആവശ്യത്തിലധികമോ?', 'result.guidance': 'മാർഗനിർദേശം, നിയമമല്ല', 'result.rights': 'ഇവിടെ നിങ്ങളുടെ അവകാശങ്ങൾ',
      'result.disclaimer': 'ഇത് മാർഗനിർദേശമാണ്, നിയമോപദേശമല്ല. അനുസരണ തീരുമാനങ്ങൾക്ക് യോഗ്യനായ അഭിഭാഷകനെ സമീപിക്കുക.',
      'result.stored': 'ഈ സ്കാൻ നൽകിയ ടെക്സ്റ്റ് വായിച്ചു, ഒന്നും സൂക്ഷിച്ചില്ല. റിപ്പോർട്ടൊന്നും സംഭരിച്ചിട്ടില്ല.',
      'result.translated': 'ഇംഗ്ലീഷ് ഉറവിടത്തിൽ നിന്ന് യന്ത്ര-വിവർത്തനം. ഉദ്ധരിച്ച വകുപ്പുകൾ മൂലഭാഷയിൽ തന്നെ.',
      'handoff.chip': 'സൈറ്റിൽ എത്താനായില്ല', 'handoff.title': 'ഞങ്ങൾ ഊഹിക്കില്ല.'
    },
    'od-IN': {
      'nav.what': "ଏହା କ'ଣ କରେ", 'nav.how': 'ଏହା କିପରି କାମ କରେ', 'nav.scan': 'ସାଇଟ୍ ସ୍କାନ୍ କରନ୍ତୁ', 'nav.act': 'DPDP ଆଇନ', 'nav.guide': 'ଅନୁମତି ଗାଇଡ୍', 'nav.add': 'Chrome ରେ ଯୋଡ଼ନ୍ତୁ',
      'hero.kicker': 'ଅଧିକାର \u00b7 ଆପଣଙ୍କ ଡାଟା-ଅଧିକାର ସାଥୀ', 'hero.l1': 'ଜାଣନ୍ତୁ, ସେମାନେ', 'hero.know': "କ'ଣ ଜାଣନ୍ତି", 'hero.l3': 'ଆପଣଙ୍କ ବିଷୟରେ।',
      'hero.sub': 'ଆପଣଙ୍କ ଡାଟାର ଏକ କାହାଣୀ ଅଛି। ତାହା ପଢ଼ନ୍ତୁ।', 'hero.cta2': 'ଏହା କିପରି କାମ କରେ ଦେଖନ୍ତୁ',
      'strip.h': 'ବର୍ତ୍ତମାନ ଚେଷ୍ଟା କରନ୍ତୁ। ଯେକୌଣସି ସାଇଟ୍ ସ୍କାନ୍ କରନ୍ତୁ।', 'strip.sub': 'ସାଇଟ୍\u200cର ପ୍ରାଇଭେସି କାହାଣୀର ଲାଇଭ୍ ପଠନ, ଆପଣଙ୍କ ବ୍ରାଉଜରରେ। କିଛି ସଂରକ୍ଷିତ ହୁଏ ନାହିଁ।',
      'scan.badge': 'ଲାଇଭ୍ ସ୍କାନର୍', 'scan.h1': 'ସାଇଟ୍ ସ୍କାନ୍ କରନ୍ତୁ। ତାର କାହାଣୀ ପଢ଼ନ୍ତୁ।',
      'scan.sub': 'ୱେବସାଇଟ୍ ଠିକଣା କିମ୍ବା ତାର ପ୍ରାଇଭେସି ପଲିସିର ଲେଖା ପେଷ୍ଟ କରନ୍ତୁ। ସ୍କାନ୍ ଆପଣଙ୍କ ବ୍ରାଉଜରରେ ଲାଇଭ୍ ଚାଲେ, କିଛି ରଖେ ନାହିଁ।',
      'scan.btn': 'ସ୍କାନ୍', 'scan.paste': 'କିମ୍ବା ପଲିସିର ଲେଖା ପେଷ୍ଟ କରନ୍ତୁ', 'scan.hide': 'ପେଷ୍ଟ ବକ୍ସ ଲୁଚାନ୍ତୁ', 'scan.analyse': 'ଏହି ଲେଖା ବିଶ୍ଳେଷଣ କରନ୍ତୁ',
      'scan.fetching': 'ସାଇଟ୍ ଓ ତାର ପଲିସି ପୃଷ୍ଠା ଖୋଲୁଛୁ\u2026', 'scan.reading': 'ପ୍ରକୃତ ଲେଖାକୁ DPDP ଆଇନ ସହ ମିଳାଇ ପଢ଼ୁଛୁ\u2026', 'scan.translating': 'ଆପଣଙ୍କ ଭାଷାରେ ଅନୁବାଦ ହେଉଛି\u2026',
      'result.title': 'ସ୍କାନ୍ ଫଳାଫଳ', 'tab.you': 'ଆପଣଙ୍କ ଡାଟା ବିପଦ', 'tab.site': 'DPDP ଅନୁପାଳନ',
      'result.collects': "ଏହା କ'ଣ ସଂଗ୍ରହ କରେ ବୋଲି କହେ", 'result.baseline': 'ଆବଶ୍ୟକତାଠାରୁ ଅଧିକ?', 'result.guidance': 'ମାର୍ଗଦର୍ଶନ, ଆଇନ ନୁହେଁ', 'result.rights': 'ଏଠାରେ ଆପଣଙ୍କ ଅଧିକାର',
      'result.disclaimer': 'ଏହା ମାର୍ଗଦର୍ଶନ, ଆଇନଗତ ପରାମର୍ଶ ନୁହେଁ। ଅନୁପାଳନ ନିଷ୍ପତ୍ତି ପାଇଁ ଯୋଗ୍ୟ ଓକିଲଙ୍କ ପରାମର୍ଶ ନିଅନ୍ତୁ।',
      'result.stored': 'ଏହି ସ୍କାନ୍ ଦିଆଯାଇଥିବା ଲେଖା ପଢ଼ିଲା, କିଛି ରଖିଲା ନାହିଁ। କୌଣସି ରିପୋର୍ଟ ସଂରକ୍ଷିତ ହୋଇନାହିଁ।',
      'result.translated': 'ଇଂରାଜୀ ମୂଳରୁ ଯନ୍ତ୍ର-ଅନୁବାଦିତ। ଉଦ୍ଧୃତ ଧାରା ମୂଳ ଭାଷାରେ ରହେ।',
      'handoff.chip': 'ସାଇଟ୍ ପାଖରେ ପହଞ୍ଚିପାରିଲୁ ନାହିଁ', 'handoff.title': 'ଆମେ ଅନୁମାନ କରିବୁ ନାହିଁ।'
    },
    'pa-IN': {
      'nav.what': 'ਇਹ ਕੀ ਕਰਦਾ ਹੈ', 'nav.how': 'ਇਹ ਕਿਵੇਂ ਕੰਮ ਕਰਦਾ ਹੈ', 'nav.scan': 'ਸਾਈਟ ਸਕੈਨ ਕਰੋ', 'nav.act': 'DPDP ਕਾਨੂੰਨ', 'nav.guide': 'ਇਜਾਜ਼ਤ ਗਾਈਡ', 'nav.add': 'Chrome ਵਿੱਚ ਜੋੜੋ',
      'hero.kicker': 'ਅਧਿਕਾਰ \u00b7 ਤੁਹਾਡਾ ਡਾਟਾ-ਹੱਕ ਸਾਥੀ', 'hero.l1': 'ਜਾਣੋ, ਉਹ', 'hero.know': 'ਕੀ ਜਾਣਦੇ ਹਨ', 'hero.l3': 'ਤੁਹਾਡੇ ਬਾਰੇ।',
      'hero.sub': 'ਤੁਹਾਡੇ ਡਾਟੇ ਦੀ ਇੱਕ ਕਹਾਣੀ ਹੈ। ਇਸਨੂੰ ਪੜ੍ਹੋ।', 'hero.cta2': 'ਦੇਖੋ ਇਹ ਕਿਵੇਂ ਕੰਮ ਕਰਦਾ ਹੈ',
      'strip.h': 'ਹੁਣੇ ਅਜ਼ਮਾਓ। ਕੋਈ ਵੀ ਸਾਈਟ ਸਕੈਨ ਕਰੋ।', 'strip.sub': 'ਸਾਈਟ ਦੀ ਪ੍ਰਾਈਵੇਸੀ ਕਹਾਣੀ ਦੀ ਲਾਈਵ ਪੜ੍ਹਤ, ਤੁਹਾਡੇ ਬ੍ਰਾਊਜ਼ਰ ਵਿੱਚ। ਕੁਝ ਵੀ ਸੰਭਾਲਿਆ ਨਹੀਂ ਜਾਂਦਾ।',
      'scan.badge': 'ਲਾਈਵ ਸਕੈਨਰ', 'scan.h1': 'ਸਾਈਟ ਸਕੈਨ ਕਰੋ। ਇਸਦੀ ਕਹਾਣੀ ਪੜ੍ਹੋ।',
      'scan.sub': 'ਵੈੱਬਸਾਈਟ ਦਾ ਪਤਾ ਜਾਂ ਉਸਦੀ ਪ੍ਰਾਈਵੇਸੀ ਪਾਲਿਸੀ ਦਾ ਟੈਕਸਟ ਪੇਸਟ ਕਰੋ। ਸਕੈਨ ਤੁਹਾਡੇ ਬ੍ਰਾਊਜ਼ਰ ਵਿੱਚ ਲਾਈਵ ਚੱਲਦਾ ਹੈ ਅਤੇ ਕੁਝ ਨਹੀਂ ਰੱਖਦਾ।',
      'scan.btn': 'ਸਕੈਨ', 'scan.paste': 'ਜਾਂ ਪਾਲਿਸੀ ਦਾ ਟੈਕਸਟ ਪੇਸਟ ਕਰੋ', 'scan.hide': 'ਪੇਸਟ ਬਾਕਸ ਲੁਕਾਓ', 'scan.analyse': 'ਇਸ ਟੈਕਸਟ ਦਾ ਵਿਸ਼ਲੇਸ਼ਣ ਕਰੋ',
      'scan.fetching': 'ਸਾਈਟ ਅਤੇ ਉਸਦੇ ਪਾਲਿਸੀ ਪੰਨੇ ਖੋਲ੍ਹ ਰਹੇ ਹਾਂ\u2026', 'scan.reading': 'ਅਸਲ ਟੈਕਸਟ ਨੂੰ DPDP ਕਾਨੂੰਨ ਨਾਲ ਮਿਲਾ ਕੇ ਪੜ੍ਹ ਰਹੇ ਹਾਂ\u2026', 'scan.translating': 'ਤੁਹਾਡੀ ਭਾਸ਼ਾ ਵਿੱਚ ਅਨੁਵਾਦ ਹੋ ਰਿਹਾ ਹੈ\u2026',
      'result.title': 'ਸਕੈਨ ਨਤੀਜਾ', 'tab.you': 'ਤੁਹਾਡਾ ਡਾਟਾ ਖਤਰਾ', 'tab.site': 'DPDP ਪਾਲਣਾ',
      'result.collects': 'ਇਹ ਕੀ ਇਕੱਠਾ ਕਰਨ ਦੀ ਗੱਲ ਕਹਿੰਦਾ ਹੈ', 'result.baseline': 'ਲੋੜ ਤੋਂ ਵੱਧ?', 'result.guidance': 'ਮਾਰਗਦਰਸ਼ਨ, ਕਾਨੂੰਨ ਨਹੀਂ', 'result.rights': 'ਇੱਥੇ ਤੁਹਾਡੇ ਹੱਕ',
      'result.disclaimer': 'ਇਹ ਮਾਰਗਦਰਸ਼ਨ ਹੈ, ਕਾਨੂੰਨੀ ਸਲਾਹ ਨਹੀਂ। ਪਾਲਣਾ ਦੇ ਫੈਸਲਿਆਂ ਲਈ ਯੋਗ ਵਕੀਲ ਦੀ ਸਲਾਹ ਲਓ।',
      'result.stored': 'ਇਸ ਸਕੈਨ ਨੇ ਦਿੱਤਾ ਟੈਕਸਟ ਪੜ੍ਹਿਆ ਅਤੇ ਕੁਝ ਨਹੀਂ ਰੱਖਿਆ। ਕੋਈ ਰਿਪੋਰਟ ਸੰਭਾਲੀ ਨਹੀਂ ਗਈ।',
      'result.translated': 'ਅੰਗਰੇਜ਼ੀ ਸਰੋਤ ਤੋਂ ਮਸ਼ੀਨ-ਅਨੁਵਾਦਿਤ। ਹਵਾਲਾ ਧਾਰਾਵਾਂ ਮੂਲ ਭਾਸ਼ਾ ਵਿੱਚ ਰਹਿੰਦੀਆਂ ਹਨ।',
      'handoff.chip': 'ਸਾਈਟ ਤੱਕ ਨਹੀਂ ਪਹੁੰਚ ਸਕੇ', 'handoff.title': 'ਅਸੀਂ ਅੰਦਾਜ਼ਾ ਨਹੀਂ ਲਗਾਵਾਂਗੇ।'
    },
    'ta-IN': {
      'nav.what': 'இது என்ன செய்கிறது', 'nav.how': 'இது எப்படி வேலை செய்கிறது', 'nav.scan': 'தளத்தை ஸ்கேன் செய்க', 'nav.act': 'DPDP சட்டம்', 'nav.guide': 'அனுமதி வழிகாட்டி', 'nav.add': 'Chrome-ல் சேர்க்க',
      'hero.kicker': 'அதிகார் \u00b7 உங்கள் தரவு-உரிமைத் துணை', 'hero.l1': 'அறியுங்கள், அவர்கள்', 'hero.know': 'என்ன அறிவார்கள்', 'hero.l3': 'உங்களைப் பற்றி.',
      'hero.sub': 'உங்கள் தரவுக்கு ஒரு கதை உண்டு. அதைப் படியுங்கள்.', 'hero.cta2': 'இது எப்படி வேலை செய்கிறது பாருங்கள்',
      'strip.h': 'இப்போதே முயற்சிக்கவும். எந்த தளத்தையும் ஸ்கேன் செய்யவும்.', 'strip.sub': 'தளத்தின் தனியுரிமைக் கதையின் நேரடி வாசிப்பு, உங்கள் உலாவியில். எதுவும் சேமிக்கப்படாது.',
      'scan.badge': 'நேரடி ஸ்கேனர்', 'scan.h1': 'தளத்தை ஸ்கேன் செய்யுங்கள். அதன் கதையைப் படியுங்கள்.',
      'scan.sub': 'வலைத்தள முகவரியை அல்லது அதன் தனியுரிமைக் கொள்கை உரையை ஒட்டவும். ஸ்கேன் உங்கள் உலாவியில் நேரடியாக இயங்கும், எதையும் வைத்துக்கொள்ளாது.',
      'scan.btn': 'ஸ்கேன்', 'scan.paste': 'அல்லது கொள்கை உரையை ஒட்டவும்', 'scan.hide': 'ஒட்டும் பெட்டியை மறைக்க', 'scan.analyse': 'இந்த உரையை ஆய்வு செய்க',
      'scan.fetching': 'தளத்தையும் அதன் கொள்கைப் பக்கங்களையும் அணுகுகிறோம்\u2026', 'scan.reading': 'உண்மையான உரையை DPDP சட்டத்துடன் ஒப்பிட்டு வாசிக்கிறோம்\u2026', 'scan.translating': 'உங்கள் மொழியில் மொழிபெயர்க்கப்படுகிறது\u2026',
      'result.title': 'ஸ்கேன் முடிவு', 'tab.you': 'உங்கள் தரவு அபாயம்', 'tab.site': 'DPDP இணக்கம்',
      'result.collects': 'இது என்ன சேகரிக்கிறது என்று கூறுகிறது', 'result.baseline': 'தேவைக்கு மேல்?', 'result.guidance': 'வழிகாட்டுதல், சட்டம் அல்ல', 'result.rights': 'இங்கே உங்கள் உரிமைகள்',
      'result.disclaimer': 'இது வழிகாட்டுதல், சட்ட ஆலோசனை அல்ல. இணக்க முடிவுகளுக்கு தகுதியான வழக்கறிஞரை அணுகவும்.',
      'result.stored': 'இந்த ஸ்கேன் கொடுத்த உரையை வாசித்தது, எதையும் வைத்துக்கொள்ளவில்லை. எந்த அறிக்கையும் சேமிக்கப்படவில்லை.',
      'result.translated': 'ஆங்கில மூலத்திலிருந்து இயந்திர மொழிபெயர்ப்பு. மேற்கோள் பிரிவுகள் மூல மொழியிலேயே இருக்கும்.',
      'handoff.chip': 'தளத்தை அணுக முடியவில்லை', 'handoff.title': 'நாங்கள் யூகிக்க மாட்டோம்.'
    },
    'te-IN': {
      'nav.what': 'ఇది ఏమి చేస్తుంది', 'nav.how': 'ఇది ఎలా పనిచేస్తుంది', 'nav.scan': 'సైట్ స్కాన్ చేయండి', 'nav.act': 'DPDP చట్టం', 'nav.guide': 'అనుమతుల గైడ్', 'nav.add': 'Chrome కు జోడించండి',
      'hero.kicker': 'అధికార్ \u00b7 మీ డేటా-హక్కుల తోడు', 'hero.l1': 'తెలుసుకోండి, వారు', 'hero.know': 'ఏమి తెలుసో', 'hero.l3': 'మీ గురించి.',
      'hero.sub': 'మీ డేటాకు ఒక కథ ఉంది. దాన్ని చదవండి.', 'hero.cta2': 'ఇది ఎలా పనిచేస్తుందో చూడండి',
      'strip.h': 'ఇప్పుడే ప్రయత్నించండి. ఏ సైట్\u200cనైనా స్కాన్ చేయండి.', 'strip.sub': 'సైట్ ప్రైవసీ కథ యొక్క ప్రత్యక్ష చదువు, మీ బ్రౌజర్\u200cలో. ఏదీ నిల్వ చేయబడదు.',
      'scan.badge': 'లైవ్ స్కానర్', 'scan.h1': 'సైట్ స్కాన్ చేయండి. దాని కథ చదవండి.',
      'scan.sub': 'వెబ్\u200cసైట్ చిరునామా లేదా దాని ప్రైవసీ పాలసీ టెక్స్ట్ అతికించండి. స్కాన్ మీ బ్రౌజర్\u200cలో ప్రత్యక్షంగా నడుస్తుంది, ఏదీ ఉంచుకోదు.',
      'scan.btn': 'స్కాన్', 'scan.paste': 'లేదా పాలసీ టెక్స్ట్ అతికించండి', 'scan.hide': 'పేస్ట్ బాక్స్ దాచండి', 'scan.analyse': 'ఈ టెక్స్ట్ విశ్లేషించండి',
      'scan.fetching': 'సైట్ మరియు దాని పాలసీ పేజీలను చేరుకుంటున్నాం\u2026', 'scan.reading': 'నిజమైన టెక్స్ట్\u200cను DPDP చట్టంతో పోల్చి చదువుతున్నాం\u2026', 'scan.translating': 'మీ భాషలోకి అనువదిస్తున్నాం\u2026',
      'result.title': 'స్కాన్ ఫలితం', 'tab.you': 'మీ డేటా ముప్పు', 'tab.site': 'DPDP అనుసరణ',
      'result.collects': 'ఇది ఏమి సేకరిస్తానని చెబుతుంది', 'result.baseline': 'అవసరానికి మించి?', 'result.guidance': 'మార్గదర్శకం, చట్టం కాదు', 'result.rights': 'ఇక్కడ మీ హక్కులు',
      'result.disclaimer': 'ఇది మార్గదర్శకం, న్యాయ సలహా కాదు. అనుసరణ నిర్ణయాలకు అర్హులైన న్యాయవాదిని సంప్రదించండి.',
      'result.stored': 'ఈ స్కాన్ ఇచ్చిన టెక్స్ట్ చదివింది, ఏదీ ఉంచుకోలేదు. ఏ నివేదికా నిల్వ చేయబడలేదు.',
      'result.translated': 'ఇంగ్లిష్ మూలం నుండి యంత్ర-అనువాదం. ఉదహరించిన నిబంధనలు మూల భాషలోనే ఉంటాయి.',
      'handoff.chip': 'సైట్\u200cను చేరుకోలేకపోయాం', 'handoff.title': 'మేము ఊహించము.'
    }
  };

  const KEY = 'adhikar.locale';
  const valid = (c) => LANGUAGES.some((l) => l.code === c);
  // normalize or-IN → od-IN (Sarvam convention)
  const normalize = (c) => (c === 'or-IN' ? 'od-IN' : c);

  function getLocale() {
    try {
      const stored = normalize(localStorage.getItem(KEY) || '');
      if (valid(stored)) return stored; // explicit choice always wins
      // first-load seed from navigator.language if it maps into the 11
      const nav = normalize((navigator.language || '').replace(/^(\w\w)(-.*)?$/, (m, p) => p + '-IN'));
      if (valid(nav)) return nav;
    } catch (e) {}
    return DEFAULT_LOCALE;
  }

  function setLocale(code) {
    const c = normalize(code);
    if (!valid(c)) return;
    try { localStorage.setItem(KEY, c); } catch (e) {}
    try { document.documentElement.lang = c; } catch (e) {}
  }

  function t(locale, key) {
    const b = STRINGS[locale] || {};
    // missing key → English, never a blank
    return b[key] != null ? b[key] : (STRINGS[DEFAULT_LOCALE][key] != null ? STRINGS[DEFAULT_LOCALE][key] : key);
  }

  // ===================================================================
  // Layer 1b: dynamic translation of a page's STATIC body copy.
  // Static content pages (DPDP Act, Permissions guide) carry too much
  // copy to hand-author in 10 scripts, so we translate-and-cache the same
  // way the scanner translates its dynamic output: reason/author in English,
  // translate the public prose, keep citations + numbers + brand verbatim.
  // Only headings, paragraphs, eyebrow badges and footer links are touched;
  // browser-mock UI (div/span) and statutory citation chips stay as-is.
  // ===================================================================
  const PT_PREFIX = 'adhikar.pt.'; // per-page, per-locale translation cache

  function _collectNodes(root) {
    const out = [];
    const scopes = root.querySelectorAll('section, footer');
    scopes.forEach(function (sec) {
      sec.querySelectorAll('h1,h2,h3,p,footer a,[data-t],[style*="uppercase"]').forEach(function (el) {
        if (el.closest('[data-no-t]')) return;
        if (el.querySelector('*')) return;           // leaf text only — never mixed nodes
        const txt = (el.textContent || '').trim();
        if (!txt) return;
        if (!/[A-Za-z]/.test(txt)) return;           // must have English source letters
        if (out.indexOf(el) === -1) out.push(el);
      });
    });
    return out;
  }

  function _toast(show, locale) {
    const id = 'adhikar-i18n-toast';
    let el = document.getElementById(id);
    if (show) {
      if (!el) {
        el = document.createElement('div');
        el.id = id;
        el.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#1A1A1A;color:#F3EEE4;font-family:Archivo,Helvetica,sans-serif;font-size:14px;font-weight:600;padding:12px 22px;border-radius:99px;z-index:99999;box-shadow:0 12px 34px rgba(0,0,0,0.28);display:flex;align-items:center;gap:10px';
        document.body.appendChild(el);
      }
      const b = STRINGS[locale] || {};
      el.textContent = b['scan.translating'] || 'Translating\u2026';
    } else if (el) {
      el.remove();
    }
  }

  // translatePage({ root, locale, complete, pageId }) — idempotent; safe to
  // call on every locale change. English restores pristine copy instantly.
  async function translatePage(opts) {
    opts = opts || {};
    const root = opts.root || document.body;
    const locale = normalize(opts.locale || DEFAULT_LOCALE);
    const complete = opts.complete;
    const pageId = opts.pageId || 'page';
    if (!root) return;

    // Registry of pristine English, captured once from the first (English) render.
    let nodes = root.__adhikarI18nNodes;
    if (!nodes) {
      nodes = _collectNodes(root).map(function (el) { return { el: el, en: el.textContent }; });
      root.__adhikarI18nNodes = nodes;
    }

    if (locale === DEFAULT_LOCALE) {
      nodes.forEach(function (n) { if (n.el.textContent !== n.en) n.el.textContent = n.en; });
      return;
    }

    const key = PT_PREFIX + pageId + '.' + locale;
    let cache = {};
    try { cache = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) {}

    let missing = [];
    nodes.forEach(function (n) { const s = n.en.trim(); if (s && cache[s] == null) missing.push(s); });
    missing = Array.from(new Set(missing));

    if (missing.length && complete) {
      _toast(true, locale);
      const lang = LANGUAGES.find(function (l) { return l.code === locale; });
      const name = lang ? lang.label : locale;
      const native = lang ? lang.native : '';
      const rules = 'Keep EXACTLY VERBATIM (do not translate or transliterate): statutory citations and section/rule numbers such as "Section 11", "SECTION 6", "Rule 3", "RULE 3, DPDP RULES 2025", "s.6(1)"; the acronym "DPDP"; law titles such as "Digital Personal Data Protection Act, 2023"; gazette references such as "G.S.R. 846(E)"; the product name "Adhikar"; "Chrome"; and any web domain such as "adhikar.in". Preserve all numbers, dates (e.g. "Aug 2023", "Nov 2025") and punctuation.';
      // Chunk to keep each call small enough to complete and never truncate.
      const CHUNK = 8;
      for (let i = 0; i < missing.length; i += CHUNK) {
        const batch = missing.slice(i, i + CHUNK);
        try {
          const prompt = 'Translate each string in the JSON array below into ' + name + ' (' + native + '), as written in India, for a public website about personal-data-privacy rights. Keep the meaning precise and the tone plain and human.\n\n' + rules + '\n\nReturn ONLY a JSON array of the same length (' + batch.length + ') and order, each element the translation of the corresponding input string. No markdown fences, no commentary.\n\n' + JSON.stringify(batch);
          const raw = await complete({ messages: [{ role: 'user', content: prompt }], max_tokens: 2200 });
          let str = String(raw).trim().replace(/^```(?:json)?/i, '').replace(/```$/,'').trim();
          str = str.replace(/^[\s\S]*?\[/, '[').replace(/\][^\]]*$/, ']');
          const arr = JSON.parse(str);
          if (Array.isArray(arr)) {
            batch.forEach(function (src, j) { if (arr[j] != null && String(arr[j]).trim()) cache[src] = String(arr[j]); });
            try { localStorage.setItem(key, JSON.stringify(cache)); } catch (e) {}
          }
        } catch (e) { /* this chunk stays English; others still apply */ }
        // paint whatever is cached so far, progressively
        nodes.forEach(function (n) { const s = n.en.trim(); if (cache[s] != null) n.el.textContent = cache[s]; });
      }
      _toast(false);
    }

    nodes.forEach(function (n) {
      const s = n.en.trim();
      n.el.textContent = (cache[s] != null ? cache[s] : n.en);
    });
  }

  window.ADHIKAR_I18N = { LANGUAGES: LANGUAGES, DEFAULT_LOCALE: DEFAULT_LOCALE, STRINGS: STRINGS, getLocale: getLocale, setLocale: setLocale, t: t, translatePage: translatePage };
})();
