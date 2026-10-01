/** Runs before first paint (inlined in the document head) so the chosen theme never flashes. Keep the key in sync with lib/account.ts. */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("ecstasy.theme");var d=t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light";}catch(e){}})();`;
