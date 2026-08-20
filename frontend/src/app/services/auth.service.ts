import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';

interface AuthStatus {
  required: boolean;
  authed: boolean;
}

/**
 * Candado de un solo secreto. El backend valida por cookie httponly, así que
 * aquí no guardamos el token: solo recordamos si hace falta y si ya se ha
 * entrado. `ensureStatus()` lo consulta una vez y lo cachea para el guard.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/auth';

  /** Si el backend exige candado (falso en desarrollo local sin token). */
  readonly required = signal(false);
  /** Si la sesión actual ya está autenticada. */
  readonly authed = signal(false);
  readonly needsLogin = computed(() => this.required() && !this.authed());

  private checked = false;

  /** Consulta el estado una sola vez; las siguientes llamadas usan la caché. */
  ensureStatus(): Observable<AuthStatus> {
    return this.http.get<AuthStatus>(`${this.base}/status`).pipe(
      tap((s) => {
        this.required.set(s.required);
        this.authed.set(s.authed);
        this.checked = true;
      }),
    );
  }

  get statusChecked(): boolean {
    return this.checked;
  }

  login(token: string): Observable<{ ok: boolean }> {
    return this.http
      .post<{ ok: boolean }>(`${this.base}/login`, { token })
      .pipe(tap(() => this.authed.set(true)));
  }

  logout(): Observable<{ ok: boolean }> {
    return this.http
      .post<{ ok: boolean }>(`${this.base}/logout`, {})
      .pipe(tap(() => this.authed.set(false)));
  }

  /** La marca un 401: la cookie ha caducado o el token ha cambiado. */
  markLoggedOut(): void {
    this.authed.set(false);
  }
}
