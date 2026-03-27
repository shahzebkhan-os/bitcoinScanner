import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScannerDataService } from './core/services/scanner-data.service';
import { WebsocketService } from './core/services/websocket.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  providers: [WebsocketService, ScannerDataService]
})
export class AppComponent {
  title = 'Bitcoin Scanner Dashboard';

  constructor(
    public scannerData: ScannerDataService,
    public wsService: WebsocketService
  ) {}
}
