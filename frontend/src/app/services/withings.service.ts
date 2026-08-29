import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

/** Estado de Withings: si está configurado en el servidor y conectado. */
export interface WithingsStatus {
  configured: boolean;
  connected: boolean;
}

/** Resultado de una sincronización de la báscula: pesadas creadas/actualizadas. */
export interface WithingsSyncResult {
  created: number;
  updated: number;
  /** Pesadas omitidas por respetar una corrección manual del peso. */
  skipped: number;
  seen: number;
}

@Injectable({ providedIn: 'root' })
export class WithingsService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/withings';

  status(): Observable<WithingsStatus> {
    return this.http.get<WithingsStatus>(`${this.base}/status`);
  }

  /**
   * Conecta la báscula: el flujo OAuth es una navegación de nivel superior (no
   * un XHR), porque Withings redirige fuera de la app y vuelve al callback. Por
   * eso se navega la ventana, no se llama con HttpClient.
   */
  connect(): void {
    window.location.href = `${this.base}/authorize`;
  }

  /**
   * Trae de Withings las mediciones de la báscula al histórico de peso. Con
   * `date` (YYYY-MM-DD) sincroniza solo ese día; sin ella, la ventana reciente.
   */
  sync(date?: string): Observable<WithingsSyncResult> {
    const url = date ? `${this.base}/sync?date=${date}` : `${this.base}/sync`;
    return this.http.post<WithingsSyncResult>(url, {});
  }

  disconnect(): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.base}/disconnect`, {});
  }
}
