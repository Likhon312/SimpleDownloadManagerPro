async function refresh(){
 const {enabled=false}=await browser.storage.local.get("enabled");
 document.getElementById("state").textContent=enabled?"Status: Enabled — new downloads go to SMDM.":"Status: Disabled — Firefox handles downloads.";
 document.getElementById("toggle").textContent=enabled?"Disable":"Enable interception";
}
document.getElementById("toggle").addEventListener("click",async()=>{
 const {enabled=false}=await browser.storage.local.get("enabled");
 await browser.storage.local.set({enabled:!enabled}); refresh();
});
refresh();