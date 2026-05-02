/// <reference types="vite/client" />

// Ambient declarations for Vite's ?raw query — used by the PWA
// fixture tests to read manifest / sw / main.tsx / index.html as
// plain text without depending on node:fs.
declare module "*?raw" {
  const content: string;
  export default content;
}
