import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { CoachConversation, CoachReply } from '../models/coach.model';

/** Chat con el entrenador-agente: charla libre con todos los datos como contexto. */
@Injectable({ providedIn: 'root' })
export class CoachService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/coach';

  /** Historial de la charla, para pintarla al abrir la pantalla. */
  load(): Observable<CoachConversation> {
    return this.http.get<CoachConversation>(this.base);
  }

  /** Un turno: envía la pregunta y recibe la respuesta del entrenador. */
  send(message: string): Observable<CoachReply> {
    return this.http.post<CoachReply>(`${this.base}/chat`, { message });
  }

  /** Reinicia la charla (vuelve al saludo inicial). */
  reset(): Observable<CoachConversation> {
    return this.http.delete<CoachConversation>(`${this.base}/chat`);
  }
}
