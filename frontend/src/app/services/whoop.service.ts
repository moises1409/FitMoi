import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

/** Estado del candado de Whoop: si está configurado en el servidor y conectado. */
export interface WhoopStatus {
  configured: boolean;
  connected: boolean;
}

/** Resultado de una sincronización: cuántos workouts se vieron/crearon/actualizaron. */
export interface WhoopSyncResult {
  created: number;
  updated: number;
  seen: number;
}

@Injectable({ providedIn: 'root' })
export class WhoopService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/whoop';

  status(): Observable<WhoopStatus> {
    return this.http.get<WhoopStatus>(`${this.base}/status`);
  }

  /**
   * Trae los workouts de Whoop. Con `date` (YYYY-MM-DD) sincroniza solo ese día
   * natural; sin ella, los últimos 30 días. Idempotente (dedup por external_id).
   */
  sync(date?: string): Observable<WhoopSyncResult> {
    const url = date ? `${this.base}/sync?date=${date}` : `${this.base}/sync`;
    return this.http.post<WhoopSyncResult>(url, {});
  }
}
