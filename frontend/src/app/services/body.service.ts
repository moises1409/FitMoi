import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { BodySummary } from '../models/body.model';

@Injectable({ providedIn: 'root' })
export class BodyService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/body';

  /** Última versión conocida del progreso corporal (medidas + fotos). */
  readonly summary = signal<BodySummary | null>(null);

  load(): Observable<BodySummary> {
    return this.http.get<BodySummary>(this.base).pipe(tap((s) => this.summary.set(s)));
  }

  /** Registra/corrige las medidas de un día (solo se envían los campos con valor). */
  addMeasurement(payload: Record<string, unknown>): Observable<BodySummary> {
    return this.http
      .post<BodySummary>(`${this.base}/measurements`, payload)
      .pipe(tap((s) => this.summary.set(s)));
  }

  deleteMeasurement(id: number): Observable<BodySummary> {
    return this.http
      .delete<BodySummary>(`${this.base}/measurements/${id}`)
      .pipe(tap((s) => this.summary.set(s)));
  }

  /** Sube una o varias fotos de progreso de una vez (multipart). */
  addPhotos(photos: File[], takenOn: string, note?: string): Observable<BodySummary> {
    const form = new FormData();
    for (const photo of photos) form.append('photos', photo);
    form.append('taken_on', takenOn);
    if (note?.trim()) form.append('note', note.trim());
    return this.http
      .post<BodySummary>(`${this.base}/photos`, form)
      .pipe(tap((s) => this.summary.set(s)));
  }

  deletePhoto(id: number): Observable<BodySummary> {
    return this.http
      .delete<BodySummary>(`${this.base}/photos/${id}`)
      .pipe(tap((s) => this.summary.set(s)));
  }
}
