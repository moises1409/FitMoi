import { Routes } from '@angular/router';
import { authGuard } from './auth/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'calendar', pathMatch: 'full' },
  {
    path: 'login',
    title: 'Acceso · FitMoi',
    loadComponent: () => import('./login/login.component').then(m => m.LoginComponent),
  },
  {
    path: 'add',
    title: 'Añadir · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-add/food-add.component').then(m => m.FoodAddComponent),
  },
  {
    path: 'capture',
    title: 'Foto · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-capture/food-capture.component').then(m => m.FoodCaptureComponent),
  },
  {
    path: 'describe',
    title: 'Describir · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-describe/food-describe.component').then(m => m.FoodDescribeComponent),
  },
  {
    path: 'confirm',
    title: 'Guardar comida · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-confirm/food-confirm.component').then(m => m.FoodConfirmComponent),
  },
  {
    path: 'library',
    title: 'Mi biblioteca · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-library/food-library.component').then(m => m.FoodLibraryComponent),
  },
  {
    path: 'calendar',
    title: 'Calendario · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./food-calendar/food-calendar.component').then(m => m.FoodCalendarComponent),
  },
  {
    path: 'review',
    title: 'Resumen semanal · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./weekly-review/weekly-review.component').then(m => m.WeeklyReviewComponent),
  },
  {
    path: 'profile',
    title: 'Mi perfil · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./profile-view/profile-view.component').then(m => m.ProfileViewComponent),
  },
  {
    path: 'profile/chat',
    title: 'Tu entrenador · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./profile-chat/profile-chat.component').then(m => m.ProfileChatComponent),
  },
  {
    path: 'activity',
    title: 'Registrar actividad · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./activity-form/activity-form.component').then(m => m.ActivityFormComponent),
  },
  {
    path: 'activity/detail',
    title: 'Detalle de actividad · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./activity-detail/activity-detail.component').then(m => m.ActivityDetailComponent),
  },
  {
    path: 'energy',
    title: 'Calorías gastadas · FitMoi',
    canActivate: [authGuard],
    loadComponent: () => import('./energy-form/energy-form.component').then(m => m.EnergyFormComponent),
  },
  // Rutas antiguas: la cesta se sustituyó por /confirm, /history y /log por /calendar
  { path: 'analyze', redirectTo: 'confirm' },
  { path: 'basket', redirectTo: 'confirm' },
  { path: 'history', redirectTo: 'calendar' },
  { path: 'log', redirectTo: 'calendar' },
  { path: '**', redirectTo: 'calendar' },
];
