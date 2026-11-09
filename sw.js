const V='percha-v1';
const CORE=['./','index.html','manifest.json','icon-192.png','icon-512.png','models/avatar.glb'];
const CDN=['https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js',
'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/DRACOLoader.js',
'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/geometries/DecalGeometry.js',
'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js'];
self.addEventListener('install',e=>e.waitUntil(caches.open(V).then(c=>Promise.allSettled([...CORE.map(u=>c.add(u)),...CDN.map(u=>c.add(new Request(u,{mode:'no-cors'})))])).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>clients.claim())));
self.addEventListener('fetch',e=>{const r=e.request,u=new URL(r.url);
 if(r.method!=='GET'||u.host.endsWith('supabase.co')||u.pathname.startsWith('/api/'))return;
 if(r.mode==='navigate'){e.respondWith(fetch(r).then(x=>{const cp=x.clone();caches.open(V).then(c=>c.put('index.html',cp));return x}).catch(()=>caches.match('index.html')));return}
 e.respondWith(caches.match(r).then(h=>{const n=fetch(r).then(x=>{if(x.ok||x.type==='opaque')caches.open(V).then(c=>c.put(r,x.clone()));return x}).catch(()=>h);return h||n}))});
