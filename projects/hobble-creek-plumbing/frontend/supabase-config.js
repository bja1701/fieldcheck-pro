// FieldCheck Pro — Supabase Configuration
// Fill in your project URL and anon key, then save.
// Get these from: Supabase Dashboard → Project Settings → API
//
// IMPORTANT: Do NOT commit this file to git if it contains real keys.
// Add supabase-config.js to your .gitignore.

window.SUPABASE_URL     = 'https://ftidlgjmtiyuxycaacob.supabase.co';
window.SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ0aWRsZ2ptdGl5dXh5Y2FhY29iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMwNzM1MTcsImV4cCI6MjA4ODY0OTUxN30.z_v4ygq326LhlXNrdXiGokAISYF9K63_rm2GE2xZzY8';

// API server URL — your named Cloudflare tunnel URL.
// After running `api/TUNNEL_SETUP.md` step 2, paste your stable tunnel URL here.
// Format: https://<your-tunnel-uuid>.cfargotunnel.com
// This value is permanent once the named tunnel is created.
window.API_SERVER_URL = 'https://1aadb92a-fd85-4c76-bac3-368528954a0d.cfargotunnel.com'.replace(/\/+$/, '');

// Optional: override without redeploy (browser console):
// localStorage.setItem('fieldcheck_api_override', 'https://YOUR_TUNNEL.cfargotunnel.com'); location.reload();
// To clear: localStorage.removeItem('fieldcheck_api_override');
(function () {
  try {
    var o = localStorage.getItem('fieldcheck_api_override');
    if (o && /^https:\/\//.test(o)) window.API_SERVER_URL = o.replace(/\/+$/, '');
  } catch (e) { /* ignore */ }
})();
