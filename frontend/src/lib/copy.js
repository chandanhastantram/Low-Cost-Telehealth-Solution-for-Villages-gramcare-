// Every bit of personality text in one place, so it's easy to translate
// (or to tone down if a clinic finds the goat jokes too much).

const GREETINGS = [
  { word: "Namaste", lang: "Hindi" },
  { word: "Namaskara", lang: "Kannada" },
  { word: "Vanakkam", lang: "Tamil" },
  { word: "Namaskaram", lang: "Telugu" },
  { word: "Namaskar", lang: "Marathi" },
  { word: "Nomoshkar", lang: "Bengali" },
];

export function greeting(date = new Date()) {
  const h = date.getHours();
  const part = h < 5 ? "Burning the midnight lamp" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  const g = GREETINGS[date.getDate() % GREETINGS.length];
  return { ...g, part };
}

export const LOADING_LINES = [
  "Walking over to the record room…",
  "Waiting for that one bar of signal…",
  "Dusting off the register…",
  "Asking the chai-wallah for directions…",
  "Untangling the phone charger…",
  "Counting the goats, then the records…",
  "The cycle's a bit slow on this road…",
];

export const EMPTY = {
  appointments: {
    title: "The waiting bench is empty",
    body: "Just a sleepy goat today. Book a consultation when someone needs one.",
  },
  appointmentsPatient: {
    title: "Nothing on your calendar",
    body: "Your CHW will book a consultation for you when you need one.",
  },
  queue: {
    title: "Queue clear",
    body: "No cases waiting. Pour yourself a cutting chai — you've earned it.",
  },
  myCases: {
    title: "No cases sent yet",
    body: "When a live call isn't possible, send the case from the consultation room.",
  },
  records: {
    title: "A clean first page",
    body: "No visits recorded yet. The first one gets written in the consultation room.",
  },
  audit: {
    title: "Nothing to audit",
    body: "Suspiciously quiet. Actions show up here as people use the app.",
  },
  people: { title: "Nobody here yet", body: "Onboard your first doctor or CHW." },
  facilities: { title: "No facilities yet", body: "Add the first PHC or sub-centre to get going." },
  chat: { title: "Say namaste 👋", body: "Messages stay here even if the call drops." },
};

export const TIPS = [
  "ORS: one litre of clean water, six level teaspoons of sugar, half a teaspoon of salt.",
  "A pulse oximeter reading below 90% is a red flag — refer, don't wait.",
  "Ask about tobacco and betel use at every adult visit. It matters.",
  "Children under five with fast breathing need to be seen the same day.",
  "Boiled water stays safe only if it's stored covered.",
  "Two missed antenatal visits? Worth a home visit.",
  "Write the follow-up date on the prescription and say it out loud, twice.",
];

export function tipOfTheDay(date = new Date()) {
  const day = Math.floor(date.getTime() / 86_400_000);
  return TIPS[day % TIPS.length];
}

export const CHAI_BREAK = [
  "Chai break! ☕ Stretch your shoulders, look at something far away.",
  "You found the secret chai stall. Two biscuits, no charge.",
  "Hydration check: when did you last drink water?",
];

export function errorText(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  if (!err?.response && err?.message === "Network Error") {
    return "Couldn't reach the server. Check the signal and try again.";
  }
  return err?.message || fallback;
}
