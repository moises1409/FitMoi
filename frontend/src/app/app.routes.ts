import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'log', pathMatch: 'full' },
  {
    path: 'log',
    title: 'Hoy · FitMoi',
    loadComponent: () => import('./food-log/food-log.component').then(m => m.FoodLogComponent),
  },
  {
    path: 'add',
    title: 'Añadir · FitMoi',
    loadComponent: () => import('./food-add/food-add.component').then(m => m.FoodAddComponent),
  },
  {
    path: 'capture',
    title: 'Foto · FitMoi',
    loadComponent: () => import('./food-capture/food-capture.component').then(m => m.FoodCaptureComponent),
  },
  {
    path: 'describe',
    title: 'Describir · FitMoi',
    loadComponent: () => import('./food-describe/food-describe.component').then(m => m.FoodDescribeComponent),
  },
  {
    path: 'confirm',
    title: 'Guardar comida · FitMoi',
    loadComponent: () => import('./food-confirm/food-confirm.component').then(m => m.FoodConfirmComponent),
  },
  {
    path: 'library',
    title: 'Mi biblioteca · FitMoi',
    loadComponent: () => import('./food-library/food-library.component').then(m => m.FoodLibraryComponent),
  },
  {
    path: 'calendar',
    title: 'Calendario · FitMoi',
    loadComponent: () => import('./food-calendar/food-calendar.component').then(m => m.FoodCalendarComponent),
  },
  {
    path: 'profile',
    title: 'Mi perfil · FitMoi',
    loadComponent: () => import('./profile-view/profile-view.component').then(m => m.ProfileViewComponent),
  },
  {
    path: 'profile/chat',
    title: 'Tu entrenador · FitMoi',
    loadComponent: () => import('./profile-chat/profile-chat.component').then(m => m.ProfileChatComponent),
  },
  {
    path: 'activity',
    title: 'Registrar actividad · FitMoi',
    loadComponent: () => import('./activity-form/activity-form.component').then(m => m.ActivityFormComponent),
  },
  // Rutas antiguas: la cesta se sustituyó por /confirm, /history por /calendar
  { path: 'analyze', redirectTo: 'confirm' },
  { path: 'basket', redirectTo: 'confirm' },
  { path: 'history', redirectTo: 'calendar' },
  { path: '**', redirectTo: 'log' },
];
