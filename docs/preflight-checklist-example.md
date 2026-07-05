# Example preflight checklist — airline (illustrative draft)

> ⚠️ **Illustrative only — not yet the real policy pack.** This table sketches the *shape* of a Pattern-A **preflight policy pack**: for each consequential agent action, the checks the agent should establish before firing, and a DB-invisible failure it catches. It was drafted from general domain knowledge (LLM-assisted), and is **not** yet:
> 1. **bound to the actual τ³ airline tool surface** — several rows are sub-cases of one tool (e.g. *cancel one leg* = `cancel_reservation` + scope) or may not be distinct τ³ tools at all (*close the case*, *accept alternate airport*); and
> 2. **traced to the airline policy document** — the anti-circularity requirement (each check should be justifiable from the policy the agent is already given, not invented).
>
> The verified, tool-bound, policy-traced pack is future work. This is here so a reader can see what the enumeration looks like. The nearest current material is the README's front-page 5-row example table and [`epistemic-preconditions.md`](epistemic-preconditions.md).

| Agent action | Preflight checks the agent must establish first | Example failure caught |
|---|---|---|
| **Cancel reservation** | Correct reservation identified; cancellation scope confirmed; refund/credit terms explained; user explicitly confirms cancellation | User was only asking about options, but agent cancels |
| **Change flight** | Correct itinerary and segment; new flight selected; fare difference disclosed; user accepts final price and schedule | Agent rebooks before the user agrees to a $240 increase |
| **Charge payment method** | Exact amount confirmed; payment method identified; user authorizes this charge | Agent charges the saved card without asking |
| **Issue refund** | Refund eligibility established; refund amount and destination confirmed; user understands timing | Agent promises a cash refund when only travel credit is allowed |
| **Issue travel credit** | User is eligible; value and expiration disclosed; user accepts credit instead of refund | Agent silently substitutes expiring credit for a refund |
| **Transfer to human agent** | Transfer is required or explicitly requested; reason explained; user consents where appropriate | Agent gives up and transfers a user who asked not to be transferred |
| **Cancel one leg of a trip** | Target segment confirmed; downstream itinerary effects explained; user confirms partial cancellation | Agent cancels the whole itinerary |
| **Change origin or destination** | New airports confirmed; connection and baggage implications explained; price accepted | Agent changes the destination when the user only wanted a date change |
| **Rebook after disruption** | User's priority established — earliest arrival, nonstop, same cabin, nearby airport; replacement accepted | Agent chooses the earliest flight despite the user requiring nonstop |
| **Downgrade cabin** | Downgrade disclosed; compensation or fare difference explained; explicit acceptance obtained | Agent moves business-class passenger to economy without clear consent |
| **Upgrade cabin** | Upgrade price and restrictions disclosed; payment authorized; traveler eligibility checked | Agent interprets "How much is an upgrade?" as approval |
| **Add baggage** | Number and type of bags confirmed; fee disclosed; user accepts charge | Agent adds two checked bags when the user asked for the price of one |
| **Remove baggage or ancillary** | Correct item identified; refundability explained; removal confirmed | Agent removes a prepaid bag the traveler still needs |
| **Select or change seat** | Passenger and flight segment confirmed; seat attributes and fee disclosed; user approves | Agent assigns a paid middle seat while the user was comparing options |
| **Modify passenger name** | Nature of change established — typo vs passenger substitution; identity documents checked if required | Agent attempts a prohibited traveler substitution as a spelling correction |
| **Add or remove passenger** | Correct reservation; affected traveler identified; itinerary and price consequences explained; explicit confirmation | Agent removes the wrong passenger from a family booking |
| **Apply travel insurance benefit** | Covered reason identified; required attestation or documentation obtained; limitations explained | Agent treats a birthday conflict as a covered cancellation reason |
| **Use voucher or certificate** | Voucher owner, value, expiration, restrictions, and remaining balance confirmed | Agent consumes a voucher the user wanted to save |
| **Change loyalty account details** | Customer identity verified; requested field confirmed; authorization established | Agent changes the email address after weak identity verification |
| **Redeem miles** | Account ownership verified; miles and cash amounts disclosed; redeposit rules explained; user confirms | Agent spends miles without showing the cash alternative |
| **Disclose itinerary or personal data** | Caller identity and authorization verified; disclosure scope appropriate | Agent reveals flight details to an unauthorized caller |
| **Separate passengers from one booking** | Travelers to separate identified; consequences for seats, upgrades, and irregular operations explained; consent obtained | Agent splits a child from the accompanying adult's reservation |
| **Book a new reservation** | Route, dates, passengers, cabin, total price, restrictions, and payment authorization confirmed | Agent books after the user merely asks for a quote |
| **Accept an alternate airport** | Airport, ground-transport implications, arrival time, and added cost disclosed; user accepts | Agent reroutes SFO passenger to Sacramento without explicit approval |
| **Close the case** | User's request resolved; outstanding commitments summarized; user has no unresolved question requiring action | Agent ends the interaction after denying a refund but before explaining alternatives |

## The check types (a typology worth keeping)

Reading down the "checks" column, each item is one of a few kinds — worth naming, because they're not all the same:

- **Requirement / goal** — the outcome the user needs (*arrive before 6pm*).
- **Preference** — what they'd rather have (*window seat*, *nonstop*).
- **Understanding** *(the user's epistemic state)* — does the user grasp a material consequence? (*changing the flight forfeits the fare*). An action can match a preference yet still be invalid if the user misunderstands its effect — this is *informed* consent, not just consent.
- **Consent / authorization** — what the user explicitly approved (*yes, cancel it*; *yes, charge this card*).

A complete preflight check for an action typically spans several of these.
