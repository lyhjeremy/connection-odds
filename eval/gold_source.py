"""The frozen itinerary set: 30 synthetic itineraries and their expected parse.

All 30 were written by the coding agent (Claude) for this eval; none is a real booking, and the
confirmation codes, names and flight numbers are invented. The expected legs and connections
were also written by the agent, by hand, before any model run. They are not human labels.

Each entry: id, text, expected legs as (airline, flight, origin, destination, depart, arrive)
with local times "YYYY-MM-DD HH:MM", and expected connections as
(hub, airline_in, airline_out, arrival_hour, month, layover_min, covered).
"""
I = [
("i01", """Your trip confirmation: ABC123
Flight 1 of 2  UA 1542
Tue, Mar 10, 2026
Depart: Boston (BOS) 6:00 AM
Arrive: Chicago (ORD) 7:52 AM
Flight 2 of 2  UA 2201
Tue, Mar 10, 2026
Depart: Chicago (ORD) 8:45 AM
Arrive: Denver (DEN) 10:38 AM""",
 [("UA", "1542", "BOS", "ORD", "2026-03-10 06:00", "2026-03-10 07:52"), ("UA", "2201", "ORD", "DEN", "2026-03-10 08:45", "2026-03-10 10:38")],
 [("ORD", "UA", "UA", 7, 3, 53, True)]),
("i02", """1 DL 2318 Y 14APR BOSATL HK1 0715 1012
2 DL 1544 Y 14APR ATLMSY HK1 1105 1158""",
 [("DL", "2318", "BOS", "ATL", "2026-04-14 07:15", "2026-04-14 10:12"), ("DL", "1544", "ATL", "MSY", "2026-04-14 11:05", "2026-04-14 11:58")],
 [("ATL", "DL", "DL", 10, 4, 53, True)]),
("i03", """I'm flying American from Raleigh to Charlotte on June 5, landing at 2:40pm, then AA 1880 out of Charlotte at 3:25pm to Nashville (arrives 4:15pm). The first flight is AA 5120 leaving RDU at 1:45pm.""",
 [("AA", "5120", "RDU", "CLT", "2026-06-05 13:45", "2026-06-05 14:40"), ("AA", "1880", "CLT", "BNA", "2026-06-05 15:25", "2026-06-05 16:15")],
 [("CLT", "AA", "AA", 14, 6, 45, True)]),
("i04", """WN 1203  MDW > DEN  Sat Jul 18  07:10 - 08:55
WN 2290  DEN > SMF  Sat Jul 18  09:40 - 11:20""",
 [("WN", "1203", "MDW", "DEN", "2026-07-18 07:10", "2026-07-18 08:55"), ("WN", "2290", "DEN", "SMF", "2026-07-18 09:40", "2026-07-18 11:20")],
 [("DEN", "WN", "WN", 8, 7, 45, True)]),
("i05", """Alaska Airlines  Confirmation KXJ9PL
AS 1080  Sun, Aug 2  Depart SEA 11:55 PM  Arrive BOS 8:21 AM (+1)""",
 [("AS", "1080", "SEA", "BOS", "2026-08-02 23:55", "2026-08-03 08:21")],
 []),
("i06", """DELTA  Trip: Minneapolis to Orlando
DL 1290  MSP 06:05  DTW 09:10   Sep 21 2026
DL 2433  DTW 10:00  ATL 12:05   Sep 21 2026
DL 1874  ATL 13:00  MCO 14:32   Sep 21 2026""",
 [("DL", "1290", "MSP", "DTW", "2026-09-21 06:05", "2026-09-21 09:10"), ("DL", "2433", "DTW", "ATL", "2026-09-21 10:00", "2026-09-21 12:05"),
  ("DL", "1874", "ATL", "MCO", "2026-09-21 13:00", "2026-09-21 14:32")],
 [("DTW", "DL", "DL", 9, 9, 50, True), ("ATL", "DL", "DL", 12, 9, 55, True)]),
("i07", """Flight 1: American Airlines AA 2765, Oct 3. Philadelphia (PHL) 8:00am to Dallas/Fort Worth (DFW) 10:25am.
Flight 2: Alaska Airlines AS 1403, Oct 3. DFW 11:30am to Seattle (SEA) 1:58pm.""",
 [("AA", "2765", "PHL", "DFW", "2026-10-03 08:00", "2026-10-03 10:25"), ("AS", "1403", "DFW", "SEA", "2026-10-03 11:30", "2026-10-03 13:58")],
 [("DFW", "AA", "AS", 10, 10, 65, False)]),
("i08", """UA 523 EWR-IAD 06/12/2026 dep 07:00 arr 08:05
UA 1912 IAD-SFO 06/12/2026 dep 08:30 arr 11:20""",
 [("UA", "523", "EWR", "IAD", "2026-06-12 07:00", "2026-06-12 08:05"), ("UA", "1912", "IAD", "SFO", "2026-06-12 08:30", "2026-06-12 11:20")],
 [("IAD", "UA", "UA", 8, 6, 25, False)]),
("i09", """Southwest Airlines
Flight 1452 | Houston Hobby (HOU) to Albuquerque (ABQ) | Depart Nov 6 at 9:35 AM | Arrive 10:40 AM
Flight 377 | Albuquerque (ABQ) to Las Vegas (LAS) | Depart Nov 6 at 11:25 AM | Arrive 11:40 AM""",
 [("WN", "1452", "HOU", "ABQ", "2026-11-06 09:35", "2026-11-06 10:40"), ("WN", "377", "ABQ", "LAS", "2026-11-06 11:25", "2026-11-06 11:40")],
 [("ABQ", "WN", "WN", 10, 11, 45, False)]),
("i10", """JetBlue B6 1123  JFK 6:15 AM to MCO 9:05 AM  Jan 15 2026
JetBlue B6 2207  MCO 1:30 PM to SJU 5:10 PM  Jan 15 2026""",
 [("B6", "1123", "JFK", "MCO", "2026-01-15 06:15", "2026-01-15 09:05"), ("B6", "2207", "MCO", "SJU", "2026-01-15 13:30", "2026-01-15 17:10")],
 [("MCO", "B6", "B6", 9, 1, 265, False)]),
("i11", """Frontier Airlines
F9 1234  Thu 2/19  Las Vegas (LAS) 10:45 PM - Denver (DEN) 2:05 AM +1
F9 2210  Fri 2/20  Denver (DEN) 6:30 AM - Cleveland (CLE) 11:24 AM""",
 [("F9", "1234", "LAS", "DEN", "2026-02-19 22:45", "2026-02-20 02:05"), ("F9", "2210", "DEN", "CLE", "2026-02-20 06:30", "2026-02-20 11:24")],
 [("DEN", "F9", "F9", 2, 2, 265, False)]),
("i12", """Outbound - Wed, May 13
UA 1715 SFO 7:00a -> ORD 1:12p
UA 650 ORD 2:05p -> LGA 5:20p
Return - Sun, May 17
UA 2135 LGA 3:00p -> ORD 4:38p
UA 1150 ORD 5:30p -> SFO 8:05p""",
 [("UA", "1715", "SFO", "ORD", "2026-05-13 07:00", "2026-05-13 13:12"), ("UA", "650", "ORD", "LGA", "2026-05-13 14:05", "2026-05-13 17:20"),
  ("UA", "2135", "LGA", "ORD", "2026-05-17 15:00", "2026-05-17 16:38"), ("UA", "1150", "ORD", "SFO", "2026-05-17 17:30", "2026-05-17 20:05")],
 [("ORD", "UA", "UA", 13, 5, 53, True), ("ORD", "UA", "UA", 16, 5, 52, True)]),
("i13", """Spirit NK 211 dep FLL 0640 hrs arr ATL 0850 hrs on 22 Mar
NK 1005 dep ATL 0950 hrs arr DTW 1200 hrs on 22 Mar""",
 [("NK", "211", "FLL", "ATL", "2026-03-22 06:40", "2026-03-22 08:50"), ("NK", "1005", "ATL", "DTW", "2026-03-22 09:50", "2026-03-22 12:00")],
 [("ATL", "NK", "NK", 8, 3, 60, True)]),
("i14", """Delta, December 19. Leave Salt Lake City 7:30 am on DL 1022, land in Los Angeles 8:52 am. Then DL 1537 from LA at 10:15 am to Honolulu, arriving 1:40 pm.""",
 [("DL", "1022", "SLC", "LAX", "2026-12-19 07:30", "2026-12-19 08:52"), ("DL", "1537", "LAX", "HNL", "2026-12-19 10:15", "2026-12-19 13:40")],
 [("LAX", "DL", "DL", 8, 12, 83, True)]),
("i15", "Flight\tFrom\tTo\tDate\tDeparts\tArrives\nAA 1418\tMIA\tCLT\t2026-04-27\t17:05\t19:00\nAA 2091\tCLT\tPIT\t2026-04-27\t19:45\t21:10",
 [("AA", "1418", "MIA", "CLT", "2026-04-27 17:05", "2026-04-27 19:00"), ("AA", "2091", "CLT", "PIT", "2026-04-27 19:45", "2026-04-27 21:10")],
 [("CLT", "AA", "AA", 19, 4, 45, True)]),
("i16", """United Express UA 5731 operated by SkyWest
Aug 30 · ASE 12:41 PM > DEN 1:39 PM
UA 1964 · DEN 2:35 PM > IAH 6:02 PM""",
 [("UA", "5731", "ASE", "DEN", "2026-08-30 12:41", "2026-08-30 13:39"), ("UA", "1964", "DEN", "IAH", "2026-08-30 14:35", "2026-08-30 18:02")],
 [("DEN", "UA", "UA", 13, 8, 56, True)]),
("i17", """Hi Jordan, your trip is confirmed! Confirmation #: QW7RTZ
Seats 14C / 22A. Checked bags: 1 ($35).
Leg 1 | JetBlue 515 | Boston Logan (BOS) -> Fort Lauderdale (FLL)
Departs Fri, Jan 9, 2026 at 5:59 PM | Arrives 9:17 PM
Leg 2 | JetBlue 1691 | FLL -> San Juan (SJU)
Departs 10:15 PM | Arrives Sat 1:58 AM
Total travel time 8h 59m""",
 [("B6", "515", "BOS", "FLL", "2026-01-09 17:59", "2026-01-09 21:17"), ("B6", "1691", "FLL", "SJU", "2026-01-09 22:15", "2026-01-10 01:58")],
 [("FLL", "B6", "B6", 21, 1, 58, True)]),
("i18", """DL 1405 ATL 08:00 LGA 10:20 Oct 12
DL 427 JFK 12:30 LAX 15:55 Oct 12""",
 [("DL", "1405", "ATL", "LGA", "2026-10-12 08:00", "2026-10-12 10:20"), ("DL", "427", "JFK", "LAX", "2026-10-12 12:30", "2026-10-12 15:55")],
 [("LGA", "DL", "DL", 10, 10, 130, False)]),
("i19", """Hotel confirmation: Hilton Chicago O'Hare. Check-in Mar 3, check-out Mar 5. 2 guests, 1 king bed. Confirmation 88231904.""",
 None, []),
("i20", """Southwest Airlines Flight 3381, Denver (DEN) to Phoenix (PHX), departs 5:50 p.m., arrives 7:05 p.m., Sunday, November 22
Flight 2917, Phoenix (PHX) to San Diego (SAN), departs 7:50 p.m., arrives 8:05 p.m.""",
 [("WN", "3381", "DEN", "PHX", "2026-11-22 17:50", "2026-11-22 19:05"), ("WN", "2917", "PHX", "SAN", "2026-11-22 19:50", "2026-11-22 20:05")],
 [("PHX", "WN", "WN", 19, 11, 45, True)]),
("i21", """AS 361  2026-06-28  SAN 06:00  SEA 08:41
AS 97   2026-06-28  SEA 09:45  ANC 12:05""",
 [("AS", "361", "SAN", "SEA", "2026-06-28 06:00", "2026-06-28 08:41"), ("AS", "97", "SEA", "ANC", "2026-06-28 09:45", "2026-06-28 12:05")],
 [("SEA", "AS", "AS", 8, 6, 64, True)]),
("i22", """American Eagle 4421 / Sun 03 May / SYR 6:05a / PHL 7:21a
American 772 / Sun 03 May / PHL 8:10a / MIA 11:05a""",
 [("AA", "4421", "SYR", "PHL", "2026-05-03 06:05", "2026-05-03 07:21"), ("AA", "772", "PHL", "MIA", "2026-05-03 08:10", "2026-05-03 11:05")],
 [("PHL", "AA", "AA", 7, 5, 49, True)]),
("i23", "aa 2104 dca 9:00 am - mia 11:59 am 1/24/26\naa 1302 mia 1:10 pm - sju 4:05 pm 1/24/26",
 [("AA", "2104", "DCA", "MIA", "2026-01-24 09:00", "2026-01-24 11:59"), ("AA", "1302", "MIA", "SJU", "2026-01-24 13:10", "2026-01-24 16:05")],
 [("MIA", "AA", "AA", 11, 1, 71, True)]),
("i24", """Delta Air Lines - Your Itinerary
Thu 08OCT  DL 2780  Pittsburgh PIT 1:55PM  Detroit DTW 3:40PM
Layover 1h 5m in Detroit
Thu 08OCT  DL 1196  Detroit DTW 4:45PM  Milwaukee MKE 4:52PM""",
 [("DL", "2780", "PIT", "DTW", "2026-10-08 13:55", "2026-10-08 15:40"), ("DL", "1196", "DTW", "MKE", "2026-10-08 16:45", "2026-10-08 16:52")],
 [("DTW", "DL", "DL", 15, 10, 65, True)]),
("i25", """UA 1460 | 18 Dec | HNL 22:10 | IAH 10:15 +1
UA 2410 | 19 Dec | IAH 11:20 | MSY 12:40""",
 [("UA", "1460", "HNL", "IAH", "2026-12-18 22:10", "2026-12-19 10:15"), ("UA", "2410", "IAH", "MSY", "2026-12-19 11:20", "2026-12-19 12:40")],
 [("IAH", "UA", "UA", 10, 12, 65, True)]),
("i26", """WN 1771 BNA>MDW 6:00 AM-7:35 AM 9/14/2026
WN 905 MDW>MSP 8:10 AM-9:45 AM 9/14/2026""",
 [("WN", "1771", "BNA", "MDW", "2026-09-14 06:00", "2026-09-14 07:35"), ("WN", "905", "MDW", "MSP", "2026-09-14 08:10", "2026-09-14 09:45")],
 [("MDW", "WN", "WN", 7, 9, 35, True)]),
("i27", """Southwest WN 488 dep Hartford (BDL) 12:05 PM, arr Baltimore (BWI) 1:15 PM, Apr 4
WN 2333 dep BWI 4:05 PM, arr Atlanta (ATL) 6:05 PM""",
 [("WN", "488", "BDL", "BWI", "2026-04-04 12:05", "2026-04-04 13:15"), ("WN", "2333", "BWI", "ATL", "2026-04-04 16:05", "2026-04-04 18:05")],
 [("BWI", "WN", "WN", 13, 4, 170, True)]),
("i28", """JetBlue 1004  BUF > JFK  Mon Feb 2  depart 9:25 AM  arrive 10:45 AM
JetBlue 623   JFK > LAS  Mon Feb 2  depart noon  arrive 3:20 PM""",
 [("B6", "1004", "BUF", "JFK", "2026-02-02 09:25", "2026-02-02 10:45"), ("B6", "623", "JFK", "LAS", "2026-02-02 12:00", "2026-02-02 15:20")],
 [("JFK", "B6", "B6", 10, 2, 75, True)]),
("i29", """1. UA 1188  Mon Jul 6  PDX 6:00 AM  SFO 7:52 AM
2. UA 512   Mon Jul 6  SFO 8:50 AM  DEN 12:25 PM
3. WN 1640  Mon Jul 6  DEN 1:40 PM  OMA 4:20 PM""",
 [("UA", "1188", "PDX", "SFO", "2026-07-06 06:00", "2026-07-06 07:52"), ("UA", "512", "SFO", "DEN", "2026-07-06 08:50", "2026-07-06 12:25"),
  ("WN", "1640", "DEN", "OMA", "2026-07-06 13:40", "2026-07-06 16:20")],
 [("SFO", "UA", "UA", 7, 7, 58, True), ("DEN", "UA", "WN", 12, 7, 75, False)]),
("i30", """AA 2871  Fri Dec 4  LGA 8:59 PM -> DFW 11:58 PM
AA 3290  Sat Dec 5  DFW 12:50 AM -> ELP 1:45 AM""",
 [("AA", "2871", "LGA", "DFW", "2026-12-04 20:59", "2026-12-04 23:58"), ("AA", "3290", "DFW", "ELP", "2026-12-05 00:50", "2026-12-05 01:45")],
 [("DFW", "AA", "AA", 23, 12, 52, True)]),
]
