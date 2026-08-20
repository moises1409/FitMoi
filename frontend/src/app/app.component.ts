import { Component, OnInit, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { filter } from 'rxjs';
import { MatIconModule } from '@angular/material/icon';
import { MatRippleModule } from '@angular/material/core';
import { ThemeService } from './services/theme.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatIconModule, MatRippleModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit {
  private theme = inject(ThemeService);
  private router = inject(Router);

  /** La barra inferior no tiene sentido en el login (pantalla a pantalla completa). */
  readonly showNav = signal(true);

  ngOnInit(): void {
    this.theme.init();
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => this.showNav.set(!e.urlAfterRedirects.startsWith('/login')));
  }
}
