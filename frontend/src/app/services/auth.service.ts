import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, map, of, switchMap, tap } from 'rxjs';
import { environment } from '../../environments/environment';

interface AuthStatus {
  required: boolean;
  authed: boolean;
}

/**
 * Candado de un solo secreto. El backend valida por cookie httponly; el
 * `ensureStatus()` inicial la comprueba una vez y la cachea para el guard.
 *
 * Persistencia en el móvil: la cookie es de un año, pero al "Añadir a pantalla
 * de inicio" en iOS la PWA usa un almacén de cookies aparte que puede vaciarse
 * entre lanzamientos, obligando a reescribir el token. Para evitarlo guardamos
 * el token en `localStorage` (que en una PWA instalada sí persiste) y, si al
 * arrancar la cookie se ha perdido, volvemos a entrar EN SILENCIO con él.
 *
 * Compromiso asumido a propósito: guardar el token en `localStorage` lo hace
 * legible por JavaScript (a diferencia de la cookie httponly). Es aceptable en
 * esta app personal de usuario único, en el propio teléfono, donde el token ya
 * es el único secreto; a cambio, no hay que reescribirlo nunca.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/auth';
  private readonly STORE_KEY = 'fitmoi_token';

  /** Si el backend exige candado (falso en desarrollo local sin token). */
  readonly required = signal(false);
  /** Si la sesión actual ya está autenticada. */
  readonly authed = signal(false);
  readonly needsLogin = computed(() => this.required() && !this.authed());

  private checked = false;

  /**
   * Consulta el estado una sola vez y lo cachea. Si hace falta candado, la
   * cookie no vale ya y hay un token recordado, reestablece la sesión en
   * silencio antes de resolver (así el guard no manda al login sin motivo).
   */
  ensureStatus(): Observable<AuthStatus> {
    return this.http.get<AuthStatus>(`${this.base}/status`).pipe(
      switchMap((s) => {
        this.required.set(s.required);
        this.authed.set(s.authed);

        const token = this.storedToken();
        if (s.required && !s.authed && token) {
          return this.silentLogin(token);
        }
        return of(s);
      }),
      tap(() => {
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
      .pipe(
        tap(() => {
          this.authed.set(true);
          this.rememberToken(token);
        }),
      );
  }

  logout(): Observable<{ ok: boolean }> {
    this.forgetToken();
    return this.http
      .post<{ ok: boolean }>(`${this.base}/logout`, {})
      .pipe(tap(() => this.authed.set(false)));
  }

  /** La marca un 401: la cookie ha caducado o el token ha cambiado. */
  markLoggedOut(): void {
    this.authed.set(false);
  }

  /**
   * Reentra con el token guardado sin molestar al usuario. Si el backend lo
   * rechaza (el token cambió), lo olvida para no reintentar en bucle.
   */
  private silentLogin(token: string): Observable<AuthStatus> {
    return this.http.post<{ ok: boolean }>(`${this.base}/login`, { token }).pipe(
      map(() => {
        this.authed.set(true);
        return { required: true, authed: true };
      }),
      catchError(() => {
        this.forgetToken();
        return of({ required: true, authed: false });
      }),
    );
  }

  private storedToken(): string | null {
    try {
      return localStorage.getItem(this.STORE_KEY);
    } catch {
      return null; // modo privado / almacenamiento bloqueado
    }
  }

  private rememberToken(token: string): void {
    try {
      localStorage.setItem(this.STORE_KEY, token);
    } catch {
      /* si no se puede persistir, seguimos con la cookie a secas */
    }
  }

  private forgetToken(): void {
    try {
      localStorage.removeItem(this.STORE_KEY);
    } catch {
      /* nada que limpiar */
    }
  }
}
