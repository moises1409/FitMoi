import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../services/auth.service';

/**
 * Puerta de entrada cuando el candado está activo. Pide el token compartido una
 * vez; el backend responde con una cookie httponly y ya no vuelve a pedirlo.
 */
@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, MatIconModule],
  template: `
    <div class="page login-page">
      <div class="login-card card">
        <div class="login-logo"><mat-icon>lock</mat-icon></div>
        <h1 class="login-title">FitMoi</h1>
        <p class="login-sub">Introduce tu clave de acceso para continuar.</p>

        <label class="field-label" for="token">Clave de acceso</label>
        <input
          id="token"
          class="field-input"
          type="password"
          [(ngModel)]="token"
          (keyup.enter)="submit()"
          autocomplete="current-password"
          placeholder="••••••••••••"
          [disabled]="loading()"
        />

        @if (error()) {
          <p class="login-error">{{ error() }}</p>
        }

        <button
          class="btn-primary login-btn"
          type="button"
          (click)="submit()"
          [disabled]="loading() || !token.trim()"
        >
          {{ loading() ? 'Entrando…' : 'Entrar' }}
        </button>
      </div>
    </div>
  `,
  styles: [
    `
      .login-page {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100dvh;
        padding: 24px;
      }
      .login-card {
        width: 100%;
        max-width: 360px;
        padding: 32px 24px;
        text-align: center;
      }
      .login-logo {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 56px;
        height: 56px;
        margin: 0 auto 16px;
        border-radius: 16px;
        background: var(--primary);
        color: #fff;
      }
      .login-logo mat-icon {
        font-size: 28px;
        width: 28px;
        height: 28px;
      }
      .login-title {
        margin: 0 0 4px;
        font-size: 22px;
        font-weight: 800;
        color: var(--text);
      }
      .login-sub {
        margin: 0 0 24px;
        font-size: 13.5px;
        color: var(--text-secondary);
      }
      .field-label {
        text-align: left;
      }
      .login-error {
        margin: 10px 0 0;
        font-size: 13px;
        font-weight: 600;
        color: #C62828;
      }
      .login-btn {
        width: 100%;
        margin-top: 20px;
      }
    `,
  ],
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  token = '';
  loading = signal(false);
  error = signal('');

  submit(): void {
    const value = this.token.trim();
    if (!value || this.loading()) return;

    this.loading.set(true);
    this.error.set('');
    this.auth.login(value).subscribe({
      next: () => {
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/calendar';
        this.router.navigateByUrl(returnUrl);
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(
          err?.status === 401
            ? 'Clave incorrecta. Inténtalo de nuevo.'
            : 'No se pudo conectar. Revisa tu conexión.',
        );
      },
    });
  }
}
