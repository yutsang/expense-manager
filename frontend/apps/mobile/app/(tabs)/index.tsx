import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  RefreshControl,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { reportsApi, journalsApi, type JournalEntry, type TrialBalance } from '@/lib/api';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

type MetricCard = {
  label: string;
  value: string;
  accent: string;
};

function buildMetrics(tb: TrialBalance | undefined): MetricCard[] {
  if (!tb) {
    return [
      { label: 'Cash Balance', value: '—', accent: '#10b981' },
      { label: 'AR Outstanding', value: '—', accent: '#6366f1' },
      { label: 'AP Outstanding', value: '—', accent: '#f59e0b' },
      { label: 'Open Periods', value: '—', accent: '#ec4899' },
    ];
  }

  const find = (keywords: string[]) => {
    const row = tb.accounts.find((a) =>
      keywords.some((kw) => a.name.toLowerCase().includes(kw.toLowerCase())),
    );
    return row ? row.balance : '0.00';
  };

  return [
    { label: 'Cash Balance', value: find(['cash', 'bank']), accent: '#10b981' },
    { label: 'AR Outstanding', value: find(['receivable']), accent: '#6366f1' },
    { label: 'AP Outstanding', value: find(['payable']), accent: '#f59e0b' },
    { label: 'Open Periods', value: '—', accent: '#ec4899' },
  ];
}

type MetricCardProps = {
  label: string;
  value: string;
  accent: string;
};

function MetricCardView({ label, value, accent }: MetricCardProps) {
  return (
    <View style={[styles.metricCard, { borderLeftColor: accent }]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: accent }]}>{value}</Text>
    </View>
  );
}

type JournalRowProps = {
  item: JournalEntry;
};

function JournalRow({ item }: JournalRowProps) {
  return (
    <View style={styles.journalRow}>
      <View style={styles.journalLeft}>
        <Text style={styles.journalDate}>
          {dayjs(item.entry_date).format('MMM D')}
        </Text>
        <Text style={styles.journalDesc} numberOfLines={1}>
          {item.description || item.reference}
        </Text>
      </View>
      <View style={styles.journalRight}>
        <Text style={styles.journalAmount}>{item.debit_total}</Text>
        <View
          style={[
            styles.statusBadge,
            item.status === 'posted' ? styles.statusPosted : styles.statusDraft,
          ]}
        >
          <Text style={styles.statusText}>{item.status}</Text>
        </View>
      </View>
    </View>
  );
}

export default function DashboardScreen() {
  const {
    data: tbData,
    isLoading: tbLoading,
    refetch: refetchTb,
  } = useQuery({
    queryKey: ['trialBalance'],
    queryFn: reportsApi.trialBalance,
  });

  const {
    data: journalData,
    isLoading: journalLoading,
    refetch: refetchJournals,
  } = useQuery({
    queryKey: ['journals', 5],
    queryFn: () => journalsApi.list(5),
  });

  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([refetchTb(), refetchJournals()]);
    setRefreshing(false);
  };

  const metrics = buildMetrics(tbData);
  const journals = journalData?.items ?? [];

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor="#6366f1"
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.greeting}>{getGreeting()}</Text>
          <Text style={styles.tenantName}>Aegis ERP</Text>
        </View>

        {/* Metrics grid */}
        <Text style={styles.sectionTitle}>Overview</Text>
        {tbLoading ? (
          <ActivityIndicator color="#6366f1" style={styles.loader} />
        ) : (
          <View style={styles.metricsGrid}>
            {metrics.map((m) => (
              <MetricCardView key={m.label} {...m} />
            ))}
          </View>
        )}

        {/* Recent activity */}
        <Text style={styles.sectionTitle}>Recent Journal Entries</Text>
        {journalLoading ? (
          <ActivityIndicator color="#6366f1" style={styles.loader} />
        ) : journals.length === 0 ? (
          <Text style={styles.emptyText}>No journal entries found.</Text>
        ) : (
          <View style={styles.journalList}>
            {journals.map((item) => (
              <JournalRow key={item.id} item={item} />
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 24,
  },
  greeting: {
    fontSize: 14,
    color: '#64748b',
    fontWeight: '500',
  },
  tenantName: {
    fontSize: 26,
    fontWeight: '700',
    color: '#e2e8f0',
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 12,
    marginTop: 8,
  },
  loader: {
    marginVertical: 20,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 24,
  },
  metricCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 14,
    borderLeftWidth: 3,
  },
  metricLabel: {
    fontSize: 12,
    color: '#94a3b8',
    fontWeight: '500',
    marginBottom: 6,
  },
  metricValue: {
    fontSize: 20,
    fontWeight: '700',
  },
  journalList: {
    gap: 1,
    borderRadius: 10,
    overflow: 'hidden',
  },
  journalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  journalLeft: {
    flex: 1,
    marginRight: 12,
  },
  journalDate: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '500',
    marginBottom: 2,
  },
  journalDesc: {
    fontSize: 14,
    color: '#e2e8f0',
    fontWeight: '500',
  },
  journalRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
  journalAmount: {
    fontSize: 14,
    fontWeight: '600',
    color: '#e2e8f0',
  },
  statusBadge: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  statusPosted: {
    backgroundColor: '#14532d',
  },
  statusDraft: {
    backgroundColor: '#1e3a5f',
  },
  statusText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  emptyText: {
    color: '#64748b',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 20,
  },
});
