// Billable fixture items — items that appear in the bid and should be shown/counted.
// Keep in sync with generate_output.py BILLABLE_ITEMS.
const BILLABLE_ITEMS = [
  "Toilet", "Lav", "Shower", "Shower (2nd Head)", "Tub/Shower",
  "Tub (freestanding)", "Sink/Laundry", "Sink (Kitchen)", "Washer Box",
  "Hose Bib", "Hot/Cold Hose Bib", "Drinking Fountain", "Steam Shower",
  "Adventure sink", "recir. Pump with loop", "Indirect water heater",
  "Water Softener/Basic", "Future Fixtures", "Water heater/Tankless",
  "Sink/Garage", "sink/Outdoor", "Pool utilities", "Bottle filler/inwall",
  "Water Heater/powervent", "Humidifier water supply",
  "Single Grinder sewer pump", "Duel Grinder sewer pump", "Cold Plunge",
  "Floor Drain", "Roof Drains", "Water softner/whole house filter", "Urinal",
];

const HIDE_ITEMS = [
  "Refridgerator Water-Line",
  "Ice bin hook up",
  "Misc. Sink (Laundry/Wet Bar/Shop)",
];

function isBillableItem(itemName) {
  const normalized = itemName.toLowerCase().trim();
  return BILLABLE_ITEMS.some(billable =>
    normalized.includes(billable.toLowerCase()) ||
    (billable === 'Lav' && (normalized.includes('lav') || normalized.includes('laboratory'))) ||
    (billable === 'Shower (2nd Head)' && (normalized.includes('2nd') || normalized.includes('second') || normalized.includes('slide'))) ||
    (billable === 'Sink (Kitchen)' && (normalized.includes('kitchen') && normalized.includes('sink'))) ||
    (billable === 'Sink/Laundry' && (normalized.includes('laundry') || normalized.includes('utility'))) ||
    (billable === 'Tub (freestanding)' && normalized.includes('freestanding'))
  );
}
