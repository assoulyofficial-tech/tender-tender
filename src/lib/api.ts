// API client for FastAPI backend
const API_BASE = 'http://localhost:8000';

export interface Tender {
  id: string;
  reference: string;
  title: string;
  organization: string;
  category: string;
  deadline: string;
  budget?: number;
  status: 'open' | 'closed' | 'awarded';
  source_url: string;
  created_at: string;
  updated_at: string;
}

export interface TenderDetail extends Tender {
  description?: string;
  extracted_text?: string;
  documents?: TenderDocument[];
  analysis?: TenderAnalysis;
}

export interface TenderDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed';
  extracted_text?: string;
  download_url: string;
}

export interface TenderAnalysis {
  summary?: string;
  key_requirements?: string[];
  eligibility_criteria?: string[];
  submission_requirements?: string[];
  evaluated_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TenderFilters {
  search?: string;
  status?: string;
  category?: string;
  page?: number;
  page_size?: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Tenders
  async getTenders(filters?: TenderFilters): Promise<PaginatedResponse<Tender>> {
    const params = new URLSearchParams();
    if (filters?.search) params.set('search', filters.search);
    if (filters?.status) params.set('status', filters.status);
    if (filters?.category) params.set('category', filters.category);
    if (filters?.page) params.set('page', String(filters.page));
    if (filters?.page_size) params.set('page_size', String(filters.page_size));
    
    const query = params.toString();
    return this.request<PaginatedResponse<Tender>>(`/api/tenders${query ? `?${query}` : ''}`);
  }

  async getTender(id: string): Promise<TenderDetail> {
    return this.request<TenderDetail>(`/api/tenders/${id}`);
  }

  // Health check
  async healthCheck(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/health');
  }
}

export const api = new ApiClient(API_BASE);
