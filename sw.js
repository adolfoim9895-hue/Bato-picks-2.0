const CACHE='radar-local-v2-1';
const SHELL=['./','./index.html','./styles.css','./app.js','./manifest.webmanifest','./icon.svg','./icon-192.png','./icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const request=e.request;
  if(request.method!=='GET'||new URL(request.url).origin!==self.location.origin)return;
  if(new URL(request.url).pathname.endsWith('/data/predictions.json')){
    e.respondWith(fetch(request).then(response=>{
      if(response.ok){const copy=response.clone();caches.open(CACHE).then(c=>c.put('./data/predictions.json',copy));}
      return response;
    }).catch(()=>caches.match('./data/predictions.json')));
    return;
  }
  e.respondWith(caches.match(request).then(cached=>cached||fetch(request)));
});
