import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../api.service';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration, ChartOptions } from 'chart.js';
import { Subject, interval, forkJoin } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, BaseChartDirective],
  template: `
    <div class="app-layout">
      <!-- SIDEBAR -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <span class="logo-icon"></span>
          <span class="logo-text">Tele<span>SaaS</span></span>
        </div>
        
        <nav class="menu">
          <button [class.active]="activeTab === 'general'" (click)="activeTab = 'general'">📈 Огляд</button>
          <button [class.active]="activeTab === 'clicks'" (click)="activeTab = 'clicks'">🖱️ Аналіз кліків</button>
          <button [class.active]="activeTab === 'builder'" (click)="activeTab = 'builder'">🛠️ Конструктор</button>
          <button [class.active]="activeTab === 'funnels'" (click)="activeTab = 'funnels'">🌪️ Мої воронки</button>
          <button [class.active]="activeTab === 'script'" (click)="activeTab = 'script'">💻 Інтеграція</button>
        </nav>

        <button class="logout-btn" (click)="logout()">Вийти</button>
      </aside>

      <!-- MAIN CONTENT -->
      <main class="main-content">
        <header class="top-bar">
          <h1>{{ getTitle() }}</h1>
          <div class="badge">AppId: {{ appId }}</div>
        </header>

        <div class="content-scroll">
          
          <!-- ТАБ: ОГЛЯД -->
          <div *ngIf="activeTab === 'general'" class="fade-in">
            <div class="date-filter-bar shadow-card">
              <div class="filter-group">
                <label>З:</label> <input type="date" [(ngModel)]="dateFrom" (change)="onDateChange()">
                <label>По:</label> <input type="date" [(ngModel)]="dateTo" (change)="onDateChange()">
              </div>
              <div class="filter-info"><small>Оновлення щохвилини</small></div>
            </div>

            <div class="stats-grid">
              <div class="stat-card">
                <span class="label">Всього подій</span>
                <div class="value">{{ stats?.totalEvents || 0 }}</div>
              </div>
              <div class="stat-card">
                <span class="label">Унікальні сесії</span>
                <div class="value text-blue">{{ stats?.uniqueUsers || 0 }}</div>
              </div>
            </div>

            <div class="charts-grid-main">
              <div class="shadow-card chart-activity">
                <h3>Динаміка активності за період</h3>
                <div style="height: 300px;"><canvas baseChart [data]="lineChartData" [options]="lineChartOptions" [type]="'line'"></canvas></div>
              </div>
              <div class="shadow-card chart-types">
                <h3>Розподіл типів подій</h3>
                <div style="height: 300px;"><canvas baseChart [data]="pieChartData" [options]="pieChartOptions" [type]="'doughnut'"></canvas></div>
              </div>
            </div>
          </div>

          <!-- ТАБ: АНАЛІЗ КЛІКІВ -->
          <div *ngIf="activeTab === 'clicks'" class="fade-in">
            <div class="shadow-card">
              <h3>ТОП-5 активних сторінок (URL)</h3>
              <div style="height: 250px;"><canvas baseChart [data]="barChartData" [options]="barChartOptions" [type]="'bar'"></canvas></div>
            </div>

            <div class="shadow-card">
              <h3>Детальна аналітика кліків</h3>
              <table class="modern-table">
                <thead><tr><th>Елемент</th><th>Сторінка</th><th>Кількість</th></tr></thead>
                <tbody>
                  <tr *ngFor="let item of clickStats">
                    <td><span class="el-badge">{{ item.element }}</span></td>
                    <td><code>{{ item.url }}</code></td>
                    <td><strong>{{ item.clicks }}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- ТАБ: КОНСТРУКТОР -->
          <div *ngIf="activeTab === 'builder'" class="fade-in">
            <div class="builder-grid">
              <div class="shadow-card">
                <h3>1. Доступні події</h3>
                <div class="source-list">
                  <div *ngFor="let el of availableElements" class="source-item" (click)="addStep(el.element)">
                    {{ el.element }} <span>➕</span>
                  </div>
                </div>
              </div>
              <div class="shadow-card">
                <h3>2. Конфігурація воронки</h3>
                <input class="modern-input" [(ngModel)]="newFunnelName" placeholder="Назва воронки">
                <div class="drop-zone">
                  <div *ngFor="let step of selectedSteps; let i = index" class="step-pill">
                    <span class="num">{{ i + 1 }}</span> {{ step }}
                    <button (click)="removeStep(i)" class="remove-btn">✕</button>
                  </div>
                  <div *ngIf="selectedSteps.length === 0" class="empty-hint">Виберіть події зліва</div>
                </div>
                <button class="save-btn" [disabled]="!newFunnelName || selectedSteps.length < 2" (click)="saveFunnel()">💾 Зберегти воронку</button>
              </div>
            </div>
          </div>

          <!-- ТАБ: МОЇ ВОРОНКИ -->
          <div *ngIf="activeTab === 'funnels'" class="fade-in">
            <div class="mode-switch-container shadow-card">
              <span class="mode-label">📊 Аналізувати за:</span>
              <div class="segmented-control">
                <button [class.active]="funnelMode === 'unique'" (click)="setFunnelMode('unique')">👤 Людьми</button>
                <button [class.active]="funnelMode === 'total'" (click)="setFunnelMode('total')">🖱️ Кліками</button>
              </div>
            </div>

            <div *ngIf="loadingFunnels" class="loader-container"><div class="spinner"></div></div>

            <ng-container *ngIf="!loadingFunnels">
              <div *ngFor="let f of customFunnels" class="shadow-card funnel-card">
                <h3>{{ f.funnelName }}</h3>
                <div class="funnel-viz">
                  <div *ngFor="let step of f.data; let i = index" class="funnel-step">
                    <div class="bar" [style.width.%]="100 - (i * 12)">
                      <span>{{ step.stepName }}</span> <strong>{{ step.count }} {{ funnelMode === 'unique' ? 'кор.' : 'кл.' }}</strong>
                    </div>
                    <div class="conv" *ngIf="i < f.data.length - 1">▼ Конверсія: {{ getConv(f.data[i].count, f.data[i+1].count) }}%</div>
                  </div>
                </div>
              </div>
            </ng-container>
          </div>

          <!-- ТАБ: СКРИПТ (ВИПРАВЛЕНО) -->
          <div *ngIf="activeTab === 'script'" class="fade-in shadow-card">
            <h3>🚀 Код інтеграції</h3>
            <p class="hint">Скопіюйте цей код та вставте його перед закриваючим тегом <code>&lt;/head&gt;</code> на вашому сайті.</p>
            <pre><code [innerText]="integrationCode"></code></pre>
          </div>
        </div>
      </main>
    </div>
  `,
  styles: [`
    :host { --primary: #4361ee; --secondary: #4cc9f0; --bg: #f8f9fc; --dark: #1e1e2d; --text: #2d3436; }
    .app-layout { display: flex; height: 100vh; background: var(--bg); font-family: 'Inter', sans-serif; color: var(--text); }
    
    .sidebar { width: 260px; background: var(--dark); color: white; padding: 25px; display: flex; flex-direction: column; }
    .sidebar-header { padding-bottom: 40px; font-size: 24px; font-weight: 800; }
    .sidebar-header span { color: var(--primary); }
    .menu { flex-grow: 1; display: flex; flex-direction: column; gap: 10px; }
    .menu button { background: none; border: none; color: #a2a3b7; padding: 12px; text-align: left; cursor: pointer; border-radius: 12px; transition: 0.3s; }
    .menu button.active { background: var(--primary); color: white; box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3); }
    .logout-btn { background: #ff4757; color: white; border: none; padding: 12px; border-radius: 10px; cursor: pointer; font-weight: bold; margin-top: auto; }

    .main-content { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
    .top-bar { background: white; padding: 20px 40px; border-bottom: 1px solid #e3e6f0; display: flex; justify-content: space-between; align-items: center; }
    .content-scroll { padding: 30px; overflow-y: auto; flex-grow: 1; }

    .charts-grid-main { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
    .date-filter-bar { display: flex; align-items: center; gap: 20px; padding: 15px 25px; margin-bottom: 25px; }
    .filter-group input { padding: 8px; border-radius: 8px; border: 1px solid #ddd; margin: 0 5px; }

    .segmented-control { display: flex; background: #edf2f7; padding: 4px; border-radius: 10px; border: 1px solid #e2e8f0; }
    .segmented-control button { border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; background: transparent; font-weight: 600; color: #718096; transition: 0.2s; }
    .segmented-control button.active { background: white; color: var(--primary); box-shadow: 0 4px 6px rgba(0,0,0,0.05); }

    .shadow-card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 8px 24px rgba(0,0,0,0.05); margin-bottom: 25px; }
    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin-bottom: 25px; }
    .stat-card { background: white; padding: 25px; border-radius: 15px; border-left: 5px solid var(--primary); }
    .stat-card .value { font-size: 32px; font-weight: 800; }

    .modern-table { width: 100%; border-collapse: collapse; }
    .modern-table td, .modern-table th { text-align: left; padding: 12px; border-bottom: 1px solid #f1f3f9; }
    .el-badge { background: #eaecf4; padding: 5px 10px; border-radius: 6px; font-weight: 600; }
    
    .builder-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; }
    .source-list { height: 350px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
    .source-item { background: #f8f9fa; padding: 12px; border-radius: 10px; cursor: pointer; display: flex; justify-content: space-between; border: 1px solid transparent; }
    .source-item:hover { border-color: var(--primary); transform: translateX(5px); transition: 0.2s; }
    .modern-input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 15px; box-sizing: border-box; }
    .drop-zone { background: #f8f9fc; border: 2px dashed #ddd; border-radius: 10px; min-height: 120px; padding: 15px; margin-bottom: 15px; }
    .step-pill { background: var(--primary); color: white; padding: 8px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; justify-content: space-between; }
    .save-btn { width: 100%; background: #1cc88a; color: white; border: none; padding: 14px; border-radius: 10px; font-weight: bold; cursor: pointer; }

    .funnel-viz { display: flex; flex-direction: column; align-items: center; padding-top: 20px; }
    .bar { background: var(--primary); color: white; padding: 15px 25px; border-radius: 10px; display: flex; justify-content: space-between; min-width: 300px; }
    .conv { margin: 12px 0; font-weight: 800; color: var(--primary); font-size: 13px; }

    .fade-in { animation: fadeIn 0.4s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10deg); } to { opacity: 1; transform: translateY(0); } }
    .spinner { width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: auto; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    pre { background: #1a1a2e; color: #e2e8f0; padding: 25px; border-radius: 15px; overflow-x: auto; border-left: 5px solid var(--primary); font-family: 'Courier New', monospace; line-height: 1.5; }
    .hint { color: #6b7280; font-size: 14px; margin-bottom: 10px; }
    code { background: #f3f4f6; padding: 2px 5px; border-radius: 4px; font-weight: 600; color: #374151; }
  `]
})
export class DashboardComponent implements OnInit, OnDestroy {
  activeTab = 'general'; appId = ''; stats: any; clickStats: any[] = []; availableElements: any[] = [];
  customFunnels: any[] = []; loadingFunnels = false; funnelMode: 'unique' | 'total' = 'unique';
  dateFrom = ''; dateTo = ''; newFunnelName = ''; selectedSteps: string[] = [];
  
  // Змінна для збереження тексту скрипта
  integrationCode = '';

  private destroy$ = new Subject<void>();

  // Charts Configs
  public lineChartData: ChartConfiguration<'line'>['data'] = {
    datasets: [
      { data: [], label: 'Всього подій', borderColor: '#4361ee', backgroundColor: 'rgba(67, 97, 238, 0.1)', fill: true, tension: 0.4 },
      { data: [], label: 'Унікальні сесії', borderColor: '#4cc9f0', backgroundColor: 'transparent', tension: 0.4 }
    ], labels: []
  };
  public lineChartOptions: ChartOptions<'line'> = { responsive: true, maintainAspectRatio: false };

  public pieChartData: ChartConfiguration<'doughnut'>['data'] = {
    labels: ['Кліки', 'Перегляди'],
    datasets: [{ data: [], backgroundColor: ['#4361ee', '#4cc9f0'] }]
  };
  public pieChartOptions: ChartOptions<'doughnut'> = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } };

  public barChartData: ChartConfiguration<'bar'>['data'] = {
    labels: [],
    datasets: [{ data: [], label: 'Активність', backgroundColor: '#4361ee', borderRadius: 8 }]
  };
  public barChartOptions: ChartOptions<'bar'> = { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } } };

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  ngOnInit() {
    this.appId = this.api.getAppId() || '';
    
    // Формуємо рядок коду інтеграції
    this.integrationCode = `<script>
  window.TeleAppId = "${this.appId}";
  (function() {
    var s = document.createElement('script');
    s.src = "https://localhost:7236/tracker.js";
    s.async = true;
    document.head.appendChild(s);
  })();
</script>`;

    const today = new Date(); const lastWeek = new Date(); lastWeek.setDate(today.getDate() - 7);
    this.dateTo = today.toISOString().split('T')[0]; this.dateFrom = lastWeek.toISOString().split('T')[0];
    this.loadData();
    interval(60000).pipe(takeUntil(this.destroy$)).subscribe(() => this.loadData());
  }

  ngOnDestroy() { this.destroy$.next(); this.destroy$.complete(); }
  onDateChange() { this.loadData(); }

  loadData() {
    forkJoin({
      stats: this.api.getStats(),
      clicks: this.api.getClickStats(),
      daily: this.api.getDailyChart(this.dateFrom, this.dateTo)
    }).pipe(takeUntil(this.destroy$)).subscribe(res => {
      this.stats = res.stats;
      this.clickStats = res.clicks ?? [];
      this.availableElements = res.clicks ?? [];

      const clicks = res.stats.eventsByType?.find((e:any) => e.eventType === 'click')?.count || 0;
      const views = res.stats.eventsByType?.find((e:any) => e.eventType === 'page_view')?.count || 0;
      this.pieChartData = { ...this.pieChartData, datasets: [{ ...this.pieChartData.datasets[0], data: [clicks, views] }] };

      const urlMap = new Map<string, number>();
      this.clickStats.forEach(item => urlMap.set(item.url, (urlMap.get(item.url) || 0) + item.clicks));
      const sorted = [...urlMap.entries()].sort((a,b) => b[1] - a[1]).slice(0, 5);
      this.barChartData = { labels: sorted.map(x => x[0]), datasets: [{ ...this.barChartData.datasets[0], data: sorted.map(x => x[1]) }] };

      this.lineChartData = {
        labels: res.daily.map((x: any) => x.date),
        datasets: [
          { ...this.lineChartData.datasets[0], data: res.daily.map((x: any) => x.totalEvents) },
          { ...this.lineChartData.datasets[1], data: res.daily.map((x: any) => x.uniqueSessions) }
        ]
      };
      
      this.cdr.detectChanges();
    });
    this.loadFunnels();
  }

  loadFunnels() {
    this.loadingFunnels = true;
    this.api.getCustomFunnels(this.funnelMode).subscribe(res => { this.customFunnels = res ?? []; this.loadingFunnels = false; });
  }

  setFunnelMode(mode: 'unique' | 'total') {
    if (this.funnelMode === mode) return;
    this.funnelMode = mode;
    this.loadFunnels();
  }

  addStep(name: string) { this.selectedSteps.push(name); }
  removeStep(index: number) { this.selectedSteps.splice(index, 1); }
  saveFunnel() {
    this.api.saveCustomFunnel({ name: this.newFunnelName, steps: this.selectedSteps }).subscribe(() => {
      alert('Воронку створено!'); this.activeTab = 'funnels'; this.loadFunnels(); this.selectedSteps = []; this.newFunnelName = '';
    });
  }

  getConv(c: number, n: number) { return c === 0 ? 0 : Math.round((n / c) * 100); }
  getTitle() {
    const titles:any = { general: 'Загальний огляд', clicks: 'Аналіз кліків', builder: 'Конструктор', funnels: 'Аналіз конверсії', script: 'Код інтеграції' };
    return titles[this.activeTab];
  }
  logout() { this.api.logout(); }
}