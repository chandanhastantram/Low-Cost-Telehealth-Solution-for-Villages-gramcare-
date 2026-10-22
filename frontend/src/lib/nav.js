import {
  CalendarPlus,
  ClipboardList,
  House,
  Inbox,
  ScrollText,
  Settings2,
  UserPlus,
  UserRound,
} from "lucide-react";

const ALL = {
  home: { to: "/dashboard", label: "Today", short: "Today", icon: House, hint: "Your register for the day" },
  register: { to: "/patients/new", label: "Register patient", short: "Register", icon: UserPlus, hint: "Add someone new to the register" },
  book: { to: "/book", label: "Book consult", short: "Book", icon: CalendarPlus, hint: "Find a doctor and a slot" },
  queue: { to: "/store-forward", label: "Case queue", short: "Queue", icon: Inbox, hint: "Store-and-forward cases" },
  myCases: { to: "/store-forward", label: "My cases", short: "Cases", icon: Inbox, hint: "Cases you sent and the replies" },
  records: { to: "/my-records", label: "My records", short: "Records", icon: ClipboardList, hint: "Your visits and prescriptions" },
  admin: { to: "/admin", label: "Admin desk", short: "Admin", icon: Settings2, hint: "People, facilities, onboarding" },
  audit: { to: "/audit-log", label: "Audit trail", short: "Audit", icon: ScrollText, hint: "Who did what, when" },
  profile: { to: "/profile", label: "Profile & PIN", short: "Profile", icon: UserRound, hint: "Language, name and offline PIN" },
};

const BY_ROLE = {
  patient: ["home", "records", "profile"],
  chw: ["home", "register", "book", "myCases", "profile"],
  doctor: ["home", "queue", "profile"],
  admin: ["home", "register", "book", "queue", "admin", "audit", "profile"],
};

export function navFor(role) {
  return (BY_ROLE[role] || ["home", "profile"]).map((k) => ALL[k]);
}
