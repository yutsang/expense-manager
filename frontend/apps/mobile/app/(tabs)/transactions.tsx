import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { journalsApi, type JournalEntry } from '@/lib/api';

function StatusBadge({ status }: { status: string }) {
  return (
    <View
      style={[
        styles.badge,
        status === 'posted' ? styles.badgePosted : styles.badgeDraft,
      ]}
    >
      <Text style={styles.badgeText}>{status}</Text>
    </View>
  );
}

function JournalRow({ item }: { item: JournalEntry }) {
  return (
    <View style={styles.row}>
      <View style={styles.rowLeft}>
        <Text style={styles.rowDate}>{dayjs(item.entry_date).format('MMM D, YYYY')}</Text>
        <Text style={styles.rowDesc} numberOfLines={2}>
          {item.description || item.reference}
        </Text>
        <StatusBadge status={item.status} />
      </View>
      <Text style={styles.rowAmount}>{item.debit_total}</Text>
    </View>
  );
}

export default function TransactionsScreen() {
  const [search, setSearch] = useState('');

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['journals', 50],
    queryFn: () => journalsApi.list(50),
  });

  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  const filtered = useMemo(() => {
    const items = data?.items ?? [];
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(
      (j) =>
        j.description?.toLowerCase().includes(q) ||
        j.reference?.toLowerCase().includes(q),
    );
  }, [data, search]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Transactions</Text>
        <TextInput
          style={styles.searchInput}
          placeholder="Search by description…"
          placeholderTextColor="#64748b"
          value={search}
          onChangeText={setSearch}
          clearButtonMode="while-editing"
          autoCorrect={false}
        />
      </View>

      {isLoading ? (
        <ActivityIndicator color="#6366f1" style={styles.loader} />
      ) : (
        <FlatList<JournalEntry>
          data={filtered}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <JournalRow item={item} />}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#6366f1"
            />
          }
          ListEmptyComponent={
            <Text style={styles.emptyText}>
              {search ? 'No results for your search.' : 'No transactions found.'}
            </Text>
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    gap: 12,
  },
  headerTitle: {
    fontSize: 26,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  searchInput: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#e2e8f0',
  },
  loader: {
    marginTop: 40,
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 40,
    gap: 8,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 14,
  },
  rowLeft: {
    flex: 1,
    marginRight: 12,
    gap: 4,
  },
  rowDate: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '500',
  },
  rowDesc: {
    fontSize: 14,
    color: '#e2e8f0',
    fontWeight: '500',
    lineHeight: 19,
  },
  rowAmount: {
    fontSize: 15,
    fontWeight: '700',
    color: '#e2e8f0',
    marginTop: 2,
  },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  badgePosted: {
    backgroundColor: '#14532d',
  },
  badgeDraft: {
    backgroundColor: '#1e3a5f',
  },
  badgeText: {
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
    paddingVertical: 40,
  },
});
