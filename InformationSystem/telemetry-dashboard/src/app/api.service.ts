import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = 'https://localhost:7236/api'; 
  constructor(private http: HttpClient, private router: Router) {}

  login(credentials: any) { return this.http.post<{token: string, appId: string}>(`${this.baseUrl}/auth/login`, credentials); }
  register(data: any) { return this.http.post(`${this.baseUrl}/auth/register`, data); }
  saveToken(token: string) { localStorage.setItem('jwt_token', token); }
  logout() { localStorage.clear(); this.router.navigate(['/login']); }
  isLoggedIn() { return !!localStorage.getItem('jwt_token'); }
  getAppId() { return localStorage.getItem('appId'); }

  getStats() { return this.http.get<any>(`${this.baseUrl}/telemetry/stats`); }
  getClickStats() { return this.http.get<any>(`${this.baseUrl}/telemetry/clicks`); }

  getUrlStats() { return this.http.get<any[]>(`${this.baseUrl}/telemetry/url-stats`); }
  
  // Оновлено: приймає дати
  getDailyChart(from: string, to: string) { 
    return this.http.get<any[]>(`${this.baseUrl}/telemetry/daily?from=${from}&to=${to}`); 
  }
  
  getAvailableElements() { return this.http.get<any[]>(`${this.baseUrl}/telemetry/available-elements`); }
  saveCustomFunnel(funnel: any) { return this.http.post(`${this.baseUrl}/telemetry/funnels`, funnel); }
  getCustomFunnels(mode: string) { return this.http.get<any[]>(`${this.baseUrl}/telemetry/custom-funnels?mode=${mode}`); }
}