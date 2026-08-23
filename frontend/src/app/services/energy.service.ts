import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { EnergyDayResponse, EnergyEntry } from '../models/energy.model';

@Injectable({ providedIn: 'root' })
export class EnergyService {
  private http = inject(HttpClient);
  private base = environment.apiUrl + '/energy';

  /** Gasto de un día concreto (YYYY-MM-DD); `entry` es null si no hay. */
  getDay(date: string): Observable<EnergyDayResponse> {
    return this.http.get<EnergyDayResponse>(`${this.base}/day`, {
      params: new HttpParams().set('date', date),
    });
  }

  /** Registra o corrige el gasto de un día. Una entrada por día. */
  save(body: { calories: number; measured_on: string; note?: string }): Observable<EnergyEntry> {
    return this.http.post<EnergyEntry>(this.base, body);
  }

  remove(id: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.base}/${id}`);
  }
}
