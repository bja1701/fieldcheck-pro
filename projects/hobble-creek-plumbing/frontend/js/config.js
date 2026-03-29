// Local pipeline server for corrections/confirm (only reachable from local server)
const _LOCAL_API = window.location.port === '8080' ? '' : 'http://100.121.253.22:8080';

// Email is a Supabase Edge Function — HTTPS, works from Vercel or local
const _SUPABASE_FN = 'https://ftidlgjmtiyuxycaacob.supabase.co/functions/v1';

window.APP_CONFIG = Object.freeze({
  tabs: ['bid', 'cabinets', 'reports'],
  floors: ['all', 'basement', 'main', 'upper'],
  planFloors: ['basement', 'main', 'upper'],
  reportTypes: [
    { value: 'all', label: 'All Types' },
    { value: 'missingFromBid', label: 'Missing from Bid' },
    { value: 'extraInBid', label: 'Extra in Bid' }
  ],
  planPdfPath: 'plans.pdf',
  apiBase: _LOCAL_API,
  sendReportUrl: _SUPABASE_FN + '/send-report',
});
