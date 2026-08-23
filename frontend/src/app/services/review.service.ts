import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { WeeklyReviewListItem, WeeklyReviewResponse } from '../models/review.model';

@Injectable({ providedIn: 'root' })
export class ReviewService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/review';

  /** Resumen de la semana que contiene `date` (YYYY-MM-DD). Se genera solo si
   *  la semana ya está cerrada; si no, devuelve una vista previa en vivo. */
  getWeekly(date: string): Observable<WeeklyReviewResponse> {
    return this.http.get<WeeklyReviewResponse>(`${this.base}/weekly`, {
      params: new HttpParams().set('date', date),
    });
  }

  /** Fuerza el recálculo y la reescritura de la semana. */
  regenerate(date: string): Observable<WeeklyReviewResponse> {
    return this.http.post<WeeklyReviewResponse>(`${this.base}/weekly/regenerate`, { date });
  }

  /** Semanas ya guardadas, de la más reciente a la más antigua. */
  list(limit = 26): Observable<{ items: WeeklyReviewListItem[] }> {
    return this.http.get<{ items: WeeklyReviewListItem[] }>(`${this.base}/weekly/list`, {
      params: new HttpParams().set('limit', limit),
    });
  }
}
