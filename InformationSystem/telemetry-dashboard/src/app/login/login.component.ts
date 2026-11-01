import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { ApiService } from '../api.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-header">
          <div class="logo">📊</div>
          <h1>Вітаємо знову!</h1>
          <p>Увійдіть, щоб керувати своєю телеметрією</p>
        </div>

        <form (ngSubmit)="onSubmit()" class="auth-form">
          <div class="input-group">
            <label>Електронна пошта</label>
            <input type="email" [(ngModel)]="email" name="email" placeholder="example@mail.com" required>
          </div>

          <div class="input-group">
            <label>Пароль</label>
            <input type="password" [(ngModel)]="password" name="password" placeholder="••••••••" required>
          </div>

          <div class="error-box" *ngIf="error">
            <span>⚠️</span> {{ error }}
          </div>

          <button type="submit" [disabled]="loading" class="submit-btn">
            {{ loading ? 'Вхід...' : 'Увійти в систему' }}
          </button>
        </form>

        <div class="auth-footer">
          <p>Немає акаунту? <a routerLink="/register">Створити зараз</a></p>
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { --primary: #4f46e5; --primary-hover: #4338ca; --bg: #f9fafb; --text-main: #111827; --text-muted: #6b7280; }
    
    .auth-page { 
      min-height: 100vh; display: flex; align-items: center; justify-content: center; 
      background: radial-gradient(circle at top left, #eef2ff 0%, #f9fafb 100%);
      font-family: 'Inter', sans-serif;
    }

    .auth-card { 
      background: white; width: 100%; max-width: 400px; padding: 40px; 
      border-radius: 20px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      animation: slideUp 0.5s ease-out;
    }

    @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

    .auth-header { text-align: center; margin-bottom: 32px; }
    .logo { font-size: 40px; margin-bottom: 16px; }
    h1 { font-size: 24px; font-weight: 700; color: var(--text-main); margin: 0; }
    .auth-header p { color: var(--text-muted); margin-top: 8px; font-size: 14px; }

    .auth-form { display: flex; flex-direction: column; gap: 20px; }
    .input-group { display: flex; flex-direction: column; gap: 6px; }
    .input-group label { font-size: 14px; font-weight: 600; color: #374151; }
    
    input { 
      padding: 12px 16px; border: 1px solid #d1d5db; border-radius: 10px; font-size: 15px;
      transition: all 0.2s; outline: none;
    }
    input:focus { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.1); }

    .error-box { 
      background: #fef2f2; color: #dc2626; padding: 12px; border-radius: 10px; 
      font-size: 14px; display: flex; gap: 8px; align-items: center; 
    }

    .submit-btn { 
      background: var(--primary); color: white; padding: 12px; border: none; 
      border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer;
      transition: background 0.2s, transform 0.1s; margin-top: 10px;
    }
    .submit-btn:hover { background: var(--primary-hover); }
    .submit-btn:active { transform: scale(0.98); }
    .submit-btn:disabled { opacity: 0.7; cursor: not-allowed; }

    .auth-footer { text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid #f3f4f6; }
    .auth-footer p { font-size: 14px; color: var(--text-muted); }
    .auth-footer a { color: var(--primary); font-weight: 600; text-decoration: none; }
    .auth-footer a:hover { text-decoration: underline; }
  `]
})
export class LoginComponent {
  email = ''; password = ''; error = ''; loading = false;
  constructor(private api: ApiService, private router: Router) {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('appId');
  }
  onSubmit() {
    this.loading = true;
    this.api.login({ email: this.email, password: this.password }).subscribe({
      next: (res: any) => {
        this.api.saveToken(res.token);
        localStorage.setItem('appId', res.appId);
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.error = err.error?.message || 'Невірний email або пароль';
        this.loading = false;
      }
    });
  }
}