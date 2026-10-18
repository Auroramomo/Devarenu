// Firefox ohne Grafikkarte, fuer die Pruefstaende (0.5.2).
//
// Wird als user.js in jedes Wegwerfprofil kopiert, das ein Pruefstand
// anlegt (pultbilder.mjs, hoererbilder.mjs, zwischenspeicher_test.py).
// Firefox kennt --disable-gpu nicht -- das ist ein Chromium-Schalter.
// Mit ihm auf der Befehlszeile endete --screenshot still ohne Bild.
// Hier das Gleichwertige; dazu setzen die Aufrufer Mesa als GL-Anbieter
// (__GLX_VENDOR_LIBRARY_NAME, __EGL_VENDOR_LIBRARY_FILENAMES,
// LIBGL_ALWAYS_SOFTWARE), damit der NVIDIA-Treiber gar nicht erst
// geladen wird, und CUDA_VISIBLE_DEVICES leer.
user_pref("layers.acceleration.disabled", true);
user_pref("gfx.webrender.software", true);
user_pref("webgl.disabled", true);
user_pref("media.hardware-video-decoding.enabled", false);
