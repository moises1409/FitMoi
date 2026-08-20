import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { ChatResponse, UserProfile } from '../models/profile.model';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/profile';

  /** Última versión conocida: la comparten la ficha y el chat. */
  readonly profile = signal<UserProfile | null>(null);

  load(): Observable<UserProfile> {
    return this.http.get<UserProfile>(this.base).pipe(tap((p) => this.profile.set(p)));
  }

  /** Edición manual de cualquier campo. */
  update(changes: Partial<UserProfile>): Observable<UserProfile> {
    return this.http.patch<UserProfile>(this.base, changes).pipe(tap((p) => this.profile.set(p)));
  }

  send(message: string): Observable<ChatResponse> {
    return this.http
      .post<ChatResponse>(`${this.base}/chat`, { message })
      .pipe(tap((res) => this.profile.set(res.profile)));
  }

  /** Registra una pesada. Una por día: repetirla corrige la anterior. */
  addWeight(weight_kg: number, measured_on?: string): Observable<UserProfile> {
    return this.http
      .post<UserProfile>(`${this.base}/weight`, { weight_kg, measured_on })
      .pipe(tap((p) => this.profile.set(p)));
  }

  deleteWeight(id: number): Observable<UserProfile> {
    return this.http
      .delete<UserProfile>(`${this.base}/weight/${id}`)
      .pipe(tap((p) => this.profile.set(p)));
  }

  /** Reinicia la conversación conservando los datos ya recogidos. */
  resetChat(): Observable<UserProfile> {
    return this.http.delete<UserProfile>(`${this.base}/chat`).pipe(tap((p) => this.profile.set(p)));
  }
}
