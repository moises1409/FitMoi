import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  DayResponse,
  FoodAnalysis,
  FoodLog,
  LogsPage,
  SummaryResponse,
  TodayResponse,
} from '../models/food.model';

@Injectable({ providedIn: 'root' })
export class FoodService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/food';

  /** Una o varias vistas del mismo plato, con descripción opcional.
   *  Más ángulos reducen el error al estimar el peso de las porciones. */
  analyzePhotos(photos: File[], description = ''): Observable<FoodAnalysis> {
    const form = new FormData();
    for (const photo of photos) form.append('photos', photo);
    if (description.trim()) form.append('description', description.trim());
    return this.http.post<FoodAnalysis>(`${this.base}/analyze`, form);
  }

  /** Descripción sola: sin coste de visión. */
  analyzeText(description: string): Observable<FoodAnalysis> {
    return this.http.post<FoodAnalysis>(`${this.base}/analyze`, {
      description: description.trim(),
    });
  }

  saveLog(payload: Record<string, unknown>): Observable<FoodLog> {
    return this.http.post<FoodLog>(`${this.base}/log`, payload);
  }

  getToday(): Observable<TodayResponse> {
    return this.http.get<TodayResponse>(`${this.base}/logs/today`);
  }

  /** Comidas de un día concreto (YYYY-MM-DD). */
  getDay(date: string): Observable<DayResponse> {
    return this.http.get<DayResponse>(`${this.base}/logs/day`, {
      params: new HttpParams().set('date', date),
    });
  }

  /** Totales por día para un rango: alimenta las vistas de semana y mes. */
  getSummary(from: string, to: string): Observable<SummaryResponse> {
    return this.http.get<SummaryResponse>(`${this.base}/summary`, {
      params: new HttpParams().set('from', from).set('to', to),
    });
  }

  getLogs(page = 1, perPage = 20): Observable<LogsPage> {
    const params = new HttpParams().set('page', page).set('per_page', perPage);
    return this.http.get<LogsPage>(`${this.base}/logs`, { params });
  }

  deleteLog(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.base}/logs/${id}`);
  }

  getPhotoUrl(filename: string): string {
    return `${environment.apiUrl}/food/uploads/${filename}`;
  }
}
