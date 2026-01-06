import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api, Tender, TenderFilters } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Search, RefreshCw, AlertCircle, ExternalLink } from 'lucide-react';

const Tenders = () => {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<TenderFilters>({
    page: 1,
    page_size: 20,
  });
  const [totalPages, setTotalPages] = useState(1);
  const [searchInput, setSearchInput] = useState('');

  const fetchTenders = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getTenders(filters);
      setTenders(response.items);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch tenders');
      setTenders([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenders();
  }, [filters]);

  const handleSearch = () => {
    setFilters(prev => ({ ...prev, search: searchInput, page: 1 }));
  };

  const handleStatusFilter = (status: string) => {
    setFilters(prev => ({
      ...prev,
      status: status === 'all' ? undefined : status,
      page: 1,
    }));
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'open':
        return 'default';
      case 'closed':
        return 'secondary';
      case 'awarded':
        return 'outline';
      default:
        return 'secondary';
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('fr-MA', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatBudget = (budget?: number) => {
    if (!budget) return '-';
    return new Intl.NumberFormat('fr-MA', {
      style: 'currency',
      currency: 'MAD',
      maximumFractionDigits: 0,
    }).format(budget);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">Appels d'Offres</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Source: marchespublics.gov.ma | Catégorie: Fournitures
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="flex gap-2 flex-1 min-w-[300px]">
          <Input
            placeholder="Rechercher par référence ou titre..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1"
          />
          <Button onClick={handleSearch} variant="secondary">
            <Search className="h-4 w-4" />
          </Button>
        </div>

        <Select
          value={filters.status || 'all'}
          onValueChange={handleStatusFilter}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Statut" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous</SelectItem>
            <SelectItem value="open">Ouvert</SelectItem>
            <SelectItem value="closed">Fermé</SelectItem>
            <SelectItem value="awarded">Attribué</SelectItem>
          </SelectContent>
        </Select>

        <Button onClick={fetchTenders} variant="outline" disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Actualiser
        </Button>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 mb-6 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
          <div>
            <p className="font-medium text-destructive">Erreur de connexion</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
            <p className="text-xs text-muted-foreground mt-2">
              Vérifiez que le backend FastAPI est lancé sur http://localhost:8000
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[120px]">Référence</TableHead>
              <TableHead>Titre</TableHead>
              <TableHead className="w-[180px]">Organisation</TableHead>
              <TableHead className="w-[100px]">Statut</TableHead>
              <TableHead className="w-[100px]">Échéance</TableHead>
              <TableHead className="w-[120px] text-right">Budget</TableHead>
              <TableHead className="w-[80px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  Chargement...
                </TableCell>
              </TableRow>
            ) : tenders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  {error ? 'Impossible de charger les données' : 'Aucun appel d\'offres trouvé'}
                </TableCell>
              </TableRow>
            ) : (
              tenders.map((tender) => (
                <TableRow key={tender.id}>
                  <TableCell className="font-mono text-xs">{tender.reference}</TableCell>
                  <TableCell>
                    <Link
                      to={`/tenders/${tender.id}`}
                      className="hover:underline text-foreground"
                    >
                      {tender.title}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {tender.organization}
                  </TableCell>
                  <TableCell>
                    <Badge variant={getStatusVariant(tender.status)}>
                      {tender.status === 'open' ? 'Ouvert' : 
                       tender.status === 'closed' ? 'Fermé' : 'Attribué'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{formatDate(tender.deadline)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {formatBudget(tender.budget)}
                  </TableCell>
                  <TableCell>
                    <a
                      href={tender.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <Button
            variant="outline"
            size="sm"
            disabled={filters.page === 1}
            onClick={() => setFilters(prev => ({ ...prev, page: (prev.page || 1) - 1 }))}
          >
            Précédent
          </Button>
          <span className="flex items-center px-3 text-sm text-muted-foreground">
            Page {filters.page} sur {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={filters.page === totalPages}
            onClick={() => setFilters(prev => ({ ...prev, page: (prev.page || 1) + 1 }))}
          >
            Suivant
          </Button>
        </div>
      )}
    </div>
  );
};

export default Tenders;
