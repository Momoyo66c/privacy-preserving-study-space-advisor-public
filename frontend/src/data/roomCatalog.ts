import type { RoomStatus } from "../types/contracts";
import type { Language } from "../i18n";

interface LocalizedText {
  zh: string;
  en: string;
}

export interface RoomCatalogEntry {
  displayName: string;
  shortLocation: LocalizedText;
  address: string;
  openingHours: LocalizedText;
  accessNote: LocalizedText;
  image: string;
  capacity: LocalizedText;
  amenities: LocalizedText[];
  mapUrl: string;
  sourceUrl: string;
}

export interface LocalizedRoomCatalogEntry {
  displayName: string;
  shortLocation: string;
  address: string;
  openingHours: string;
  accessNote: string;
  image: string;
  capacity: string;
  amenities: string[];
  mapUrl: string;
  sourceUrl: string;
}

export const roomCatalog: Record<string, RoomCatalogEntry> = {
  room_a: {
    displayName: "ERC The Study",
    shortLocation: { zh: "教育资源中心 · 2层", en: "Education Resource Centre · Level 2" },
    address: "8 College Avenue West, Singapore 138608",
    openingHours: { zh: "学期期间 · 09:00–22:00", en: "Term time · 09:00–22:00" },
    accessNote: {
      zh: "NUS 师生 · 部分座位可通过 uNivUS 预约",
      en: "NUS students and staff · selected seats bookable in uNivUS",
    },
    image: "/rooms/nus-college-classroom-4.jpg",
    capacity: { zh: "中型学习区", en: "Medium-sized study cluster" },
    amenities: [
      { zh: "电源插座", en: "Power outlets" },
      { zh: "校园 Wi-Fi", en: "Campus Wi-Fi" },
      { zh: "独立学习位", en: "Study carrels" },
      { zh: "移动白板", en: "Mobile whiteboards" },
    ],
    mapUrl: "https://maps.google.com/?q=Education+Resource+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/campus-life/campus-services/utown/education-resource-centre/",
  },
  room_b: {
    displayName: "NUS-ISS Collaborative Classroom",
    shortLocation: { zh: "NUS-ISS · 3层", en: "NUS-ISS · Level 3" },
    address: "25 Heng Mui Keng Terrace, Singapore 119615",
    openingHours: { zh: "周一至周五 · 09:00–17:00", en: "Mon–Fri · 09:00–17:00" },
    accessNote: { zh: "按教学课表开放", en: "Open according to the teaching timetable" },
    image: "/rooms/nus-college-classroom-1.jpg",
    capacity: { zh: "灵活教室", en: "Flexible classroom" },
    amenities: [
      { zh: "小组桌椅", en: "Group tables" },
      { zh: "演示显示屏", en: "Presentation display" },
      { zh: "校园 Wi-Fi", en: "Campus Wi-Fi" },
      { zh: "电源插座", en: "Power outlets" },
    ],
    mapUrl: "https://maps.google.com/?q=NUS-ISS+25+Heng+Mui+Keng+Terrace",
    sourceUrl: "https://www.iss.nus.edu.sg/about-us/facilities",
  },
  room_c: {
    displayName: "NUS-ISS Inspire Theatre",
    shortLocation: { zh: "NUS-ISS · 2至4层", en: "NUS-ISS · Levels 2–4" },
    address: "25 Heng Mui Keng Terrace, Singapore 119615",
    openingHours: { zh: "周一至周五 · 09:00–17:00", en: "Mon–Fri · 09:00–17:00" },
    accessNote: { zh: "仅限排定课程与获授权活动", en: "Scheduled classes and authorised events" },
    image: "/rooms/nus-college-classroom-2.jpg",
    capacity: { zh: "大型阶梯教室", en: "Large lecture theatre" },
    amenities: [
      { zh: "阶梯座位", en: "Tiered seating" },
      { zh: "视听系统", en: "AV system" },
      { zh: "电源插座", en: "Power outlets" },
      { zh: "无障碍通行", en: "Wheelchair access" },
    ],
    mapUrl: "https://maps.google.com/?q=NUS-ISS+25+Heng+Mui+Keng+Terrace",
    sourceUrl: "https://www.iss.nus.edu.sg/about-us/facilities",
  },
  room_d: {
    displayName: "NUS-ISS Seminar Theatre",
    shortLocation: { zh: "NUS-ISS · 4层", en: "NUS-ISS · Level 4" },
    address: "25 Heng Mui Keng Terrace, Singapore 119615",
    openingHours: { zh: "周一至周五 · 09:00–17:00", en: "Mon–Fri · 09:00–17:00" },
    accessNote: { zh: "仅限排定课程与获授权活动", en: "Scheduled classes and authorised events" },
    image: "/rooms/nus-college-classroom-3.jpg",
    capacity: { zh: "大型研讨空间", en: "Large seminar space" },
    amenities: [
      { zh: "投影系统", en: "Projection system" },
      { zh: "阶梯座位", en: "Tiered seating" },
      { zh: "校园 Wi-Fi", en: "Campus Wi-Fi" },
      { zh: "无障碍通行", en: "Wheelchair access" },
    ],
    mapUrl: "https://maps.google.com/?q=NUS-ISS+25+Heng+Mui+Keng+Terrace",
    sourceUrl: "https://www.iss.nus.edu.sg/about-us/facilities",
  },
  room_e: {
    displayName: "ERC Seminar Room 1",
    shortLocation: { zh: "教育资源中心 · 2层 · UT23-02-07", en: "Education Resource Centre · Level 2 · UT23-02-07" },
    address: "8 College Avenue West, Singapore 138608",
    openingHours: { zh: "按课表与预约时段开放", en: "Open according to teaching timetables and confirmed bookings" },
    accessNote: {
      zh: "NUS 师生 · 以课程安排或 UTown 场地预约为准",
      en: "NUS students and staff · subject to class schedules or UTown booking",
    },
    image: "/rooms/nus-erc-sr1.jpg",
    capacity: { zh: "30 人研讨教室", en: "30-seat seminar room" },
    amenities: [
      { zh: "自带设备（BYOD）", en: "Bring your own device (BYOD)" },
      { zh: "单投影系统", en: "Single projection" },
      { zh: "无线投屏", en: "Wireless presentation" },
      { zh: "HDMI 与 USB-C", en: "HDMI and USB-C" },
    ],
    mapUrl: "https://maps.google.com/?q=Education+Resource+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/wp-content/uploads/2025/02/UpdatedUTSeminar-Rooms-in-ERC.pdf",
  },
  room_f: {
    displayName: "ERC Seminar Room 2",
    shortLocation: { zh: "教育资源中心 · 2层 · UT23-02-08", en: "Education Resource Centre · Level 2 · UT23-02-08" },
    address: "8 College Avenue West, Singapore 138608",
    openingHours: { zh: "按课表与预约时段开放", en: "Open according to teaching timetables and confirmed bookings" },
    accessNote: {
      zh: "NUS 师生 · 以课程安排或 UTown 场地预约为准",
      en: "NUS students and staff · subject to class schedules or UTown booking",
    },
    image: "/rooms/nus-erc-sr2.jpg",
    capacity: { zh: "36 人研讨教室", en: "36-seat seminar room" },
    amenities: [
      { zh: "自带设备（BYOD）", en: "Bring your own device (BYOD)" },
      { zh: "单投影系统", en: "Single projection" },
      { zh: "触控面板", en: "Touch-panel AV control" },
      { zh: "无线投屏", en: "Wireless presentation" },
    ],
    mapUrl: "https://maps.google.com/?q=Education+Resource+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/wp-content/uploads/2025/02/UpdatedUTSeminar-Rooms-in-ERC.pdf",
  },
  room_g: {
    displayName: "ERC Seminar Room 8",
    shortLocation: { zh: "教育资源中心 · 2层 · UT23-02-14", en: "Education Resource Centre · Level 2 · UT23-02-14" },
    address: "8 College Avenue West, Singapore 138608",
    openingHours: { zh: "按课表与预约时段开放", en: "Open according to teaching timetables and confirmed bookings" },
    accessNote: {
      zh: "NUS 师生 · 以课程安排或 UTown 场地预约为准",
      en: "NUS students and staff · subject to class schedules or UTown booking",
    },
    image: "/rooms/nus-erc-sr8.jpg",
    capacity: { zh: "30 人协作教室", en: "30-seat collaborative classroom" },
    amenities: [
      { zh: "圆桌协作座位", en: "Round-table collaboration" },
      { zh: "Windows 11 电脑", en: "Windows 11 desktop" },
      { zh: "WACOM 互动笔屏", en: "WACOM interactive pen display" },
      { zh: "无线投屏", en: "Wireless presentation" },
    ],
    mapUrl: "https://maps.google.com/?q=Education+Resource+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/wp-content/uploads/2025/02/UpdatedUTSeminar-Rooms-in-ERC.pdf",
  },
  room_h: {
    displayName: "ERC Activity Learning Room",
    shortLocation: { zh: "教育资源中心 · 2层 · UT23-02-13", en: "Education Resource Centre · Level 2 · UT23-02-13" },
    address: "8 College Avenue West, Singapore 138608",
    openingHours: { zh: "按课表与预约时段开放", en: "Open according to teaching timetables and confirmed bookings" },
    accessNote: {
      zh: "NUS 师生 · 以课程安排或 UTown 场地预约为准",
      en: "NUS students and staff · subject to class schedules or UTown booking",
    },
    image: "/rooms/nus-erc-alr.jpg",
    capacity: { zh: "40 人主动学习教室", en: "40-seat active learning room" },
    amenities: [
      { zh: "双投影系统", en: "Dual projection" },
      { zh: "小组协作桌", en: "Group collaboration tables" },
      { zh: "WACOM 互动笔屏", en: "WACOM interactive pen display" },
      { zh: "WolfVision 实物展台", en: "WolfVision visualiser" },
    ],
    mapUrl: "https://maps.google.com/?q=Education+Resource+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/wp-content/uploads/2025/02/UpdatedUTSeminar-Rooms-in-ERC.pdf",
  },
  room_i: {
    displayName: "SRC Global Learning Room",
    shortLocation: { zh: "Stephen Riady Centre · 1层 · UT25-01-10", en: "Stephen Riady Centre · Level 1 · UT25-01-10" },
    address: "2 College Avenue West, Singapore 138607",
    openingHours: { zh: "按课表与预约时段开放", en: "Open according to teaching timetables and confirmed bookings" },
    accessNote: {
      zh: "NUS 师生 · 以课程安排或 UTown 场地预约为准",
      en: "NUS students and staff · subject to class schedules or UTown booking",
    },
    image: "/rooms/nus-src-glr.jpg",
    capacity: { zh: "80 人全球学习教室", en: "80-seat global learning room" },
    amenities: [
      { zh: "双投影系统", en: "Dual projection" },
      { zh: "阶梯协作座位", en: "Tiered collaborative seating" },
      { zh: "WACOM 互动笔屏", en: "WACOM interactive pen display" },
      { zh: "HDMI 与 USB-C", en: "HDMI and USB-C" },
    ],
    mapUrl: "https://maps.google.com/?q=Stephen+Riady+Centre+NUS",
    sourceUrl: "https://uci.nus.edu.sg/wp-content/uploads/2025/02/UpdatedUTSeminar-Rooms-in-SRC.pdf",
  },
};

export function catalogFor(room: RoomStatus, language: Language): LocalizedRoomCatalogEntry {
  const entry =
    roomCatalog[room.room_id] ??
    ({
      displayName: room.name,
      shortLocation: { zh: room.location ?? "NUS 校园学习空间", en: room.location ?? "NUS campus learning space" },
      address: room.location ?? "National University of Singapore",
      openingHours: { zh: "请查看最新校园课表", en: "Check the latest campus timetable" },
      accessNote: { zh: "适用 NUS 场地访问规则", en: "NUS access rules apply" },
      image: "/rooms/nus-college-classroom-1.jpg",
      capacity: { zh: "校园学习空间", en: "Campus learning space" },
      amenities: [
        { zh: "校园 Wi-Fi", en: "Campus Wi-Fi" },
        { zh: "学习座位", en: "Study seating" },
      ],
      mapUrl: "https://maps.google.com/?q=National+University+of+Singapore",
      sourceUrl: "https://www.nus.edu.sg/",
    } satisfies RoomCatalogEntry);

  const localize = (value: LocalizedText) => value[language];
  return {
    displayName: entry.displayName,
    shortLocation: localize(entry.shortLocation),
    address: entry.address,
    openingHours: localize(entry.openingHours),
    accessNote: localize(entry.accessNote),
    image: entry.image,
    capacity: localize(entry.capacity),
    amenities: entry.amenities.map(localize),
    mapUrl: entry.mapUrl,
    sourceUrl: entry.sourceUrl,
  };
}
