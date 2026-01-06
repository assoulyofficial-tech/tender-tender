import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, TenderDetail as TenderDetailType } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import {
  ArrowLeft,
  ExternalLink,
  FileText,
  AlertCircle,
  Download,
  Clock,
  Building,
  Calendar,
} from 'lucide-react';

const TenderDetail = () => {
  const { id } = useParams<{ id: string }>();
  const [tender, setTender] = useState<TenderDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTender = async () => {
      if (!id) return;
      setLoading(true);
      setError(null);
      try {
        const data = await api.getTender(id);
        setTender(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch tender');
      } finally {
        setLoading(false);
      }
    };
    fetchTender();
  }, [id]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('fr-MA', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatBudget = (budget?: number) => {
    if (!budget) return 'Non spécifié';
    return new Intl.NumberFormat('fr-MA', {
      style: 'currency',
      currency: 'MAD',
    }).format(budget);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getOcrStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="default">OCR terminé</Badge>;
      case 'processing':
        return <Badge variant="secondary">En cours</Badge>;
      case 'pending':
        return <Badge variant="outline">En attente</Badge>;
      case 'failed':
        return <Badge variant="destructive">Échec</Badge>;
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="text-center py-12 text-muted-foreground">
          Chargement...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Link to="/tenders">
          <Button variant="ghost" className="mb-6">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Retour à la liste
          </Button>
        </Link>
        <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
          <div>
            <p className="font-medium text-destructive">Erreur</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!tender) return null;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <Link to="/tenders">
        <Button variant="ghost" className="mb-6">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Retour à la liste
        </Button>
      </Link>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-mono text-muted-foreground mb-1">
              {tender.reference}
            </p>
            <h1 className="text-2xl font-semibold text-foreground">
              {tender.title}
            </h1>
          </div>
          <Badge
            variant={
              tender.status === 'open'
                ? 'default'
                : tender.status === 'closed'
                ? 'secondary'
                : 'outline'
            }
          >
            {tender.status === 'open'
              ? 'Ouvert'
              : tender.status === 'closed'
              ? 'Fermé'
              : 'Attribué'}
          </Badge>
        </div>
      </div>

      {/* Meta Info */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="flex items-center gap-2 text-sm">
          <Building className="h-4 w-4 text-muted-foreground" />
          <span>{tender.organization}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <span>{formatDate(tender.deadline)}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <span>Catégorie: {tender.category}</span>
        </div>
        <div className="text-sm font-mono">
          Budget: {formatBudget(tender.budget)}
        </div>
      </div>

      <a
        href={tender.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ExternalLink className="h-4 w-4" />
        Voir sur marchespublics.gov.ma
      </a>

      <Separator className="my-6" />

      {/* Description */}
      {tender.description && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{tender.description}</p>
          </CardContent>
        </Card>
      )}

      {/* Documents */}
      {tender.documents && tender.documents.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Documents ({tender.documents.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {tender.documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded-md"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium">{doc.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {doc.file_type.toUpperCase()} • {formatFileSize(doc.file_size)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {getOcrStatusBadge(doc.ocr_status)}
                    <a href={doc.download_url} target="_blank" rel="noopener noreferrer">
                      <Button variant="ghost" size="sm">
                        <Download className="h-4 w-4" />
                      </Button>
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Extracted Text */}
      {tender.extracted_text && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Texte extrait (OCR)</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs font-mono bg-muted p-4 rounded-md overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
              {tender.extracted_text}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* AI Analysis */}
      {tender.analysis && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Analyse IA (DeepSeek)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {tender.analysis.summary && (
              <div>
                <h4 className="text-sm font-medium mb-2">Résumé</h4>
                <p className="text-sm text-muted-foreground">{tender.analysis.summary}</p>
              </div>
            )}

            {tender.analysis.key_requirements && tender.analysis.key_requirements.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2">Exigences clés</h4>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                  {tender.analysis.key_requirements.map((req, i) => (
                    <li key={i}>{req}</li>
                  ))}
                </ul>
              </div>
            )}

            {tender.analysis.eligibility_criteria && tender.analysis.eligibility_criteria.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2">Critères d'éligibilité</h4>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                  {tender.analysis.eligibility_criteria.map((crit, i) => (
                    <li key={i}>{crit}</li>
                  ))}
                </ul>
              </div>
            )}

            {tender.analysis.submission_requirements && tender.analysis.submission_requirements.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2">Exigences de soumission</h4>
                <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                  {tender.analysis.submission_requirements.map((req, i) => (
                    <li key={i}>{req}</li>
                  ))}
                </ul>
              </div>
            )}

            {tender.analysis.evaluated_at && (
              <p className="text-xs text-muted-foreground">
                Analysé le {formatDate(tender.analysis.evaluated_at)}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Timestamps */}
      <div className="text-xs text-muted-foreground">
        <p>Créé: {formatDate(tender.created_at)}</p>
        <p>Mis à jour: {formatDate(tender.updated_at)}</p>
      </div>
    </div>
  );
};

export default TenderDetail;
