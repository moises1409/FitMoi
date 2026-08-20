import { Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ThemeService } from '../services/theme.service';

@Component({
  selector: 'app-theme-toggle',
  standalone: true,
  imports: [MatIconModule],
  template: `
    <button
      class="icon-btn"
      type="button"
      (click)="theme.toggle()"
      [attr.aria-label]="theme.isDark() ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'">
      <mat-icon>{{ theme.isDark() ? 'light_mode' : 'dark_mode' }}</mat-icon>
    </button>
  `,
})
export class ThemeToggleComponent {
  readonly theme = inject(ThemeService);
}
