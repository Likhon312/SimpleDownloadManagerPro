const HOST = "com.simpledownloadmanagerpro.host";

browser.runtime.onInstalled.addListener(() => {
  browser.storage.local.set({enabled: false});
});

browser.downloads.onCreated.addListener(async (item) => {
  const {enabled = false} = await browser.storage.local.get("enabled");
  if (!enabled || !item.url || !/^https?:/i.test(item.url)) return;

  try {
    // Read cookies only for this download URL; they are sent to the local native host.
    const cookies = await browser.cookies.getAll({url: item.url});
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join("; ");
    const reply = await browser.runtime.sendNativeMessage(HOST, {
      action: "add_download",
      url: item.url,
      filename: item.filename || "",
      cookie: cookieHeader
    });

    if (reply && reply.ok) {
      await browser.downloads.cancel(item.id);
      await browser.downloads.erase({id: item.id});
    } else {
      console.error("SMDM:", reply && reply.error);
    }
  } catch (err) {
    // Leave the original Firefox download intact if the connector fails.
    console.error("SMDM native host:", err);
  }
});
