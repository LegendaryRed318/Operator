import { invoke } from '@tauri-apps/api/core';
import { isPermissionGranted, requestPermission, sendNotification } from '@tauri-apps/plugin-notification';

/**
 * Universal notification helper.
 * Works in both Tauri (Native) and Browser (Web).
 */
export async function pushNotification(title: string, body: string) {
  // 1. Check if running in Tauri
  const isTauri = !!(window as any).__TAURI_INTERNALS__;

  if (isTauri) {
    try {
      // Use Tauri Plugin Notification
      let permissionGranted = await isPermissionGranted();
      if (!permissionGranted) {
        const permission = await requestPermission();
        permissionGranted = permission === 'granted';
      }

      if (permissionGranted) {
        sendNotification({ title, body });
      } else {
        // Fallback to custom command if plugin fails or permission denied
        await invoke('show_notification', { title, body });
      }
    } catch (err) {
      console.warn('[Notification] Tauri API error, falling back to console:', err);
      console.log(`[NOTIFY] ${title}: ${body}`);
    }
  } else {
    // 2. Browser Fallback
    console.log(`[WEB-NOTIFY] ${title}: ${body}`);
    
    // Attempt standard browser notification
    if ("Notification" in window) {
      if (Notification.permission === "granted") {
        new Notification(title, { body });
      } else if (Notification.permission !== "denied") {
        const permission = await Notification.requestPermission();
        if (permission === "granted") {
          new Notification(title, { body });
        }
      }
    }
  }
}
