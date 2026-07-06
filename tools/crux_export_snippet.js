// NRC Crux — browser storage export
// ----------------------------------
// Your per-puzzle solve TIME is only stored in the browser (localStorage keeps
// roughly the last week of saves; the server only keeps aggregates). To feed
// nrc_crux_fetch.py, export your storage with this snippet.
//
// HOW TO USE:
//   1. Open any Crux page while logged in:  https://www.nrc.nl/puzzels/crux/
//   2. Open DevTools -> Console.
//   3. Paste this whole snippet, press Enter, and accept the download.
//   4. It saves  crux_storage_dump.json  to ~/Downloads.
//   5. Run:  python3 nrc_crux_fetch.py
//
// Re-export + re-run any time — the script resumes and accumulates new dates.

(async () => {
  const out = { localStorage: {}, indexedDB: {} };
  for (const [k, v] of Object.entries(localStorage)) out.localStorage[k] = v;
  const dbs = (await indexedDB.databases?.().catch(() => [])) || [];
  for (const { name } of dbs) {
    out.indexedDB[name] = {};
    await new Promise((res) => {
      const req = indexedDB.open(name);
      req.onsuccess = () => {
        const db = req.result, stores = [...db.objectStoreNames];
        if (!stores.length) { db.close(); return res(); }
        const tx = db.transaction(stores, 'readonly');
        let pending = stores.length;
        for (const s of stores) {
          const g = tx.objectStore(s).getAll();
          g.onsuccess = () => { out.indexedDB[name][s] = g.result; if (--pending === 0) { db.close(); res(); } };
          g.onerror   = () => { if (--pending === 0) { db.close(); res(); } };
        }
      };
      req.onerror = () => res();
    });
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], { type: 'application/json' }));
  a.download = 'crux_storage_dump.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  console.log('Exported. localStorage keys:', Object.keys(out.localStorage).length,
              '| IndexedDB dbs:', Object.keys(out.indexedDB));
})();
