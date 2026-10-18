// Firefox fuer die Pruefstaende, ohne Grafikkarte (0.5.2).
//
// Firefox kennt --disable-gpu nicht; mit dem Schalter endete
// --screenshot still ohne Bild. Stattdessen: die Einstellungen aus
// firefox_ohne_karte.user.js ins Wegwerfprofil, und Mesa als
// GL-Anbieter, damit der NVIDIA-Treiber gar nicht erst geladen wird.
// Dasselbe fuer Python steht in hilfe.firefox_ohne_karte().

import { copyFileSync } from "node:fs";
import { join } from "node:path";

export const UMGEBUNG = {
  CUDA_VISIBLE_DEVICES: "",
  LIBGL_ALWAYS_SOFTWARE: "1",
  __GLX_VENDOR_LIBRARY_NAME: "mesa",
  __EGL_VENDOR_LIBRARY_FILENAMES: "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
};

/** Legt user.js ins Profil. Zurueck: die Umgebung fuer execFile. */
export function ohneKarte(profil) {
  copyFileSync(new URL("./firefox_ohne_karte.user.js", import.meta.url),
               join(profil, "user.js"));
  return { ...process.env, ...UMGEBUNG };
}
