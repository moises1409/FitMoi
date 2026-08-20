import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'fitmoi-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly isDark = signal(false);

  init(): void {
    const saved = localStorage.getItem(STORAGE_KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    this.apply(saved ? saved === 'dark' : prefersDark);
  }

  toggle(): void {
    const next = !this.isDark();
    localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light');
    this.apply(next);
  }

  private apply(dark: boolean): void {
    this.isDark.set(dark);
    document.body.classList.toggle('dark-theme', dark);
  }
}
