import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { FoodTemplate, LibrarySuggestions } from '../models/food.model';

/** Respuesta de las operaciones que reescriben el historial. */
export type TemplateUpdate = FoodTemplate & { logs_updated: number };

@Injectable({ providedIn: 'root' })
export class LibraryService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/library';

  /** Frecuentes en la franja horaria actual + recientes. */
  suggest(mealType: string, limit = 8): Observable<LibrarySuggestions> {
    const params = new HttpParams().set('meal_type', mealType).set('limit', limit);
    return this.http.get<LibrarySuggestions>(`${this.base}/suggest`, { params });
  }

  search(query = '', limit = 50): Observable<{ items: FoodTemplate[]; query: string }> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return this.http.get<{ items: FoodTemplate[]; query: string }>(this.base, { params });
  }

  create(body: Partial<FoodTemplate> & { name: string }): Observable<FoodTemplate> {
    return this.http.post<FoodTemplate>(this.base, body);
  }

  /** Editar propaga los cambios a los días donde aparece el alimento. */
  update(id: number, body: Partial<FoodTemplate>): Observable<TemplateUpdate> {
    return this.http.patch<TemplateUpdate>(`${this.base}/${id}`, body);
  }

  setPhoto(id: number, photo: File): Observable<TemplateUpdate> {
    const form = new FormData();
    form.append('photo', photo);
    return this.http.post<TemplateUpdate>(`${this.base}/${id}/photo`, form);
  }

  clearPhoto(id: number): Observable<FoodTemplate> {
    return this.http.delete<FoodTemplate>(`${this.base}/${id}/photo`);
  }

  /** Recalcula macros y valoración a partir de la foto guardada. */
  reanalyze(id: number): Observable<TemplateUpdate> {
    return this.http.post<TemplateUpdate>(`${this.base}/${id}/reanalyze`, {});
  }

  /** Borra del catálogo; los registros ya guardados se conservan. */
  remove(id: number): Observable<{ message: string; logs_unlinked: number }> {
    return this.http.delete<{ message: string; logs_unlinked: number }>(`${this.base}/${id}`);
  }

  /** Funde un duplicado en otra entrada, sumando su historial de uso. */
  merge(id: number, intoId: number): Observable<FoodTemplate> {
    return this.http.post<FoodTemplate>(`${this.base}/${id}/merge`, { into_id: intoId });
  }
}
