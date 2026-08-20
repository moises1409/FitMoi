import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, shareReplay, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Activity, ActivityFamily } from '../models/activity.model';

@Injectable({ providedIn: 'root' })
export class ActivityService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/activities';

  /** Familias con su color. Se piden una vez y se comparten. */
  readonly families = signal<ActivityFamily[]>([]);

  /** Petición en vuelo, para que varias pantallas a la vez no la pidan dos veces. */
  private familiesRequest?: Observable<{ families: ActivityFamily[] }>;

  loadFamilies(): Observable<{ families: ActivityFamily[] }> {
    return this.http
      .get<{ families: ActivityFamily[] }>(`${this.base}/families`)
      .pipe(tap((res) => this.families.set(res.families)));
  }

  /**
   * Carga las familias si aún no están. Sin esto, cualquier pantalla que muestre
   * actividades sin acordarse de pedirlas las pinta todas como "Otro" en oliva.
   */
  ensureFamilies(): Observable<{ families: ActivityFamily[] }> {
    if (this.families().length) return of({ families: this.families() });
    if (!this.familiesRequest) {
      this.familiesRequest = this.loadFamilies().pipe(shareReplay(1));
    }
    return this.familiesRequest;
  }

  familyOf(key: string): ActivityFamily | undefined {
    return this.families().find((f) => f.key === key);
  }

  colorOf(key: string): string {
    return this.familyOf(key)?.color ?? '#4D7C0F';
  }

  get(id: number): Observable<Activity> {
    return this.http.get<Activity>(`${this.base}/${id}`);
  }

  create(body: Partial<Activity>): Observable<Activity> {
    return this.http.post<Activity>(this.base, body);
  }

  update(id: number, body: Partial<Activity>): Observable<Activity> {
    return this.http.patch<Activity>(`${this.base}/${id}`, body);
  }

  remove(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.base}/${id}`);
  }
}
