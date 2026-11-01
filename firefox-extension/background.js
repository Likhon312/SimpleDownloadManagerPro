const HOST = "com.simpledownloadmanagerpro.host";
browser.runtime.onInstalled.addListener(() => {
  browser.storage.local.set({enabled: false});
});
browser.downloads.onCreated.addListener(async (item) => {
  const {enabled = false} = await browser.storage.local.get("enabled");
  if (!enabled || !item.url || !/^https?:/i.test(item.url)) return;
  try {
    const reply = await browser.runtime.sendNativeMessage(HOST, {
      action: "add_download",
      url: item.url,
      filename: item.filename || ""
    });
    if (reply && reply.ok) {
      await browser.downloads.cancel(item.id);
      await browser.downloads.erase({id: item.id});
    } else {
      console.error("SMDM:", reply && reply.error);
    }
  } catch (err) {
    console.error("SMDM native host:", err);
  }
});