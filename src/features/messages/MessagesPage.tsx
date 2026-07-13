import React, { useEffect, useMemo, useState } from "react";
import { Archive, Inbox, Megaphone, MessageSquare, RotateCcw, Send, UserRound, X } from "lucide-react";
import { useAuth } from "../../app/providers/AuthProvider";
import {
  supabase,
  type AdminChatConversationRow,
  type AdminChatMessageRow,
  type OrgAnnouncementRow,
  type ProfileRow,
} from "../../shared/supabase";

type Tab = "messages" | "announcements";
const ALL_ORGS_VALUE = "__all__";

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatTime(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export const MessagesPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === "Admin";
  const isSuperAdmin = user?.superAdmin === true;

  const [activeTab, setActiveTab] = useState<Tab>(isAdmin ? "messages" : "announcements");
  const [busy, setBusy] = useState(false);
  const [contacts, setContacts] = useState<ProfileRow[]>([]);
  const [conversations, setConversations] = useState<AdminChatConversationRow[]>([]);
  const [chatMessages, setChatMessages] = useState<AdminChatMessageRow[]>([]);
  const [announcements, setAnnouncements] = useState<OrgAnnouncementRow[]>([]);

  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [newChatContactId, setNewChatContactId] = useState("");
  const [replyBody, setReplyBody] = useState("");

  const [announcementOrgId, setAnnouncementOrgId] = useState(user?.orgId || "techbin");
  const [announcementAudience, setAnnouncementAudience] = useState<"org" | "all">("org");
  const [announcementTitle, setAnnouncementTitle] = useState("");
  const [announcementBody, setAnnouncementBody] = useState("");
  const [selectedAnnouncementOrgId, setSelectedAnnouncementOrgId] = useState("");
  const [showArchivedAnnouncements, setShowArchivedAnnouncements] = useState(false);

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId) || null,
    [conversations, selectedConversationId]
  );

  const selectedNewContact = useMemo(
    () => contacts.find((contact) => contact.id === newChatContactId) || null,
    [contacts, newChatContactId]
  );

  const activeConversationMessages = useMemo(
    () => chatMessages.filter((message) => message.conversation_id === selectedConversationId),
    [chatMessages, selectedConversationId]
  );

  const announcementGroups = useMemo(() => {
    const groups = new Map<string, OrgAnnouncementRow[]>();
    announcements.forEach((announcement) => {
      const groupId = announcement.audience === "all" ? ALL_ORGS_VALUE : announcement.org_id || "unknown";
      const current = groups.get(groupId) || [];
      current.push(announcement);
      groups.set(groupId, current);
    });

    return Array.from(groups.entries())
      .map(([orgId, rows]) => ({
        orgId,
        announcements: rows.sort(
          (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
        ),
      }))
      .sort((a, b) => {
        const latestA = new Date(a.announcements[0]?.created_at || 0).getTime();
        const latestB = new Date(b.announcements[0]?.created_at || 0).getTime();
        return latestB - latestA;
      });
  }, [announcements]);

  const selectedAnnouncementGroup =
    announcementGroups.find((group) => group.orgId === selectedAnnouncementOrgId) || null;

  const announcementGroupLabel = (orgId: string) =>
    orgId === ALL_ORGS_VALUE ? "All Organizations" : orgId;

  const conversationContactLabel = (conversation: AdminChatConversationRow) => {
    if (!user) return "-";
    const other =
      conversation.participant_a_id === user.uid
        ? {
            email: conversation.participant_b_email,
            orgId: conversation.participant_b_org_id,
            superAdmin: conversation.participant_b_super_admin,
          }
        : {
            email: conversation.participant_a_email,
            orgId: conversation.participant_a_org_id,
            superAdmin: conversation.participant_a_super_admin,
          };

    return `${other.email} · ${other.superAdmin ? "Super Admin" : other.orgId}`;
  };

  const loadChat = async () => {
    if (!isAdmin) return;

    const [contactsResult, conversationsResult, messagesResult] = await Promise.all([
      supabase
        .from("profiles")
        .select("*")
        .eq("role", "Admin")
        .eq("disabled", false)
        .order("email", { ascending: true }),
      supabase
        .from("admin_chat_conversations")
        .select("*")
        .order("updated_at", { ascending: false })
        .limit(100),
      supabase
        .from("admin_chat_messages")
        .select("*")
        .order("created_at", { ascending: true })
        .limit(500),
    ]);

    if (contactsResult.error) {
      console.error(contactsResult.error);
      alert("Failed to load message contacts.");
      return;
    }
    if (conversationsResult.error) {
      console.error(conversationsResult.error);
      alert("Failed to load conversations.");
      return;
    }
    if (messagesResult.error) {
      console.error(messagesResult.error);
      alert("Failed to load conversation messages.");
      return;
    }

    const visibleContacts = ((contactsResult.data || []) as ProfileRow[]).filter((contact) => {
      if (contact.id === user?.uid) return false;
      if (isSuperAdmin) return contact.super_admin !== true;
      if (contact.super_admin === true) return true;
      return contact.org_id === user?.orgId;
    });
    const nextConversations = (conversationsResult.data || []) as AdminChatConversationRow[];

    setContacts(visibleContacts);
    setNewChatContactId((current) => {
      if (current && visibleContacts.some((contact) => contact.id === current)) return current;
      return visibleContacts[0]?.id || "";
    });
    setConversations(nextConversations);
    setChatMessages((messagesResult.data || []) as AdminChatMessageRow[]);
    setSelectedConversationId((current) => {
      if (current && nextConversations.some((conversation) => conversation.id === current)) return current;
      return nextConversations[0]?.id || "";
    });
  };

  const loadAnnouncements = async () => {
    const includeArchived = isAdmin && showArchivedAnnouncements;
    const { data, error } = await supabase
      .from("org_announcements")
      .select("*")
      .eq("active", includeArchived ? false : true)
      .order("created_at", { ascending: false })
      .limit(100);

    if (error) {
      console.error(error);
      alert("Failed to load announcements.");
      return;
    }

    setAnnouncements((data || []) as OrgAnnouncementRow[]);
  };

  useEffect(() => {
    if (!user) return;

    loadChat();
    loadAnnouncements();

    const channel = supabase
      .channel(`messages:${user.superAdmin ? "all" : user.orgId}:${user.uid}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "admin_chat_conversations" }, () => loadChat())
      .on("postgres_changes", { event: "*", schema: "public", table: "admin_chat_messages" }, () => loadChat())
      .on("postgres_changes", { event: "*", schema: "public", table: "org_announcements" }, () => loadAnnouncements())
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [user?.uid, user?.orgId, user?.superAdmin, isAdmin, isSuperAdmin, showArchivedAnnouncements]);

  const createConversation = async (contact: ProfileRow) => {
    if (!user) throw new Error("No signed-in user.");

    const participants = [
      {
        id: user.uid,
        email: user.email,
        orgId: user.orgId,
        superAdmin: user.superAdmin,
      },
      {
        id: contact.id,
        email: contact.email,
        orgId: contact.org_id,
        superAdmin: contact.super_admin,
      },
    ].sort((a, b) => a.id.localeCompare(b.id));

    const orgId = contact.super_admin ? user.orgId : contact.org_id;
    const { data, error } = await supabase
      .from("admin_chat_conversations")
      .insert({
        org_id: orgId,
        participant_a_id: participants[0].id,
        participant_a_email: participants[0].email,
        participant_a_org_id: participants[0].orgId,
        participant_a_super_admin: participants[0].superAdmin,
        participant_b_id: participants[1].id,
        participant_b_email: participants[1].email,
        participant_b_org_id: participants[1].orgId,
        participant_b_super_admin: participants[1].superAdmin,
        created_by: user.uid,
      })
      .select("*")
      .single();
    if (error) throw error;
    return data as AdminChatConversationRow;
  };

  const findConversationForContact = (contact: ProfileRow) => {
    if (!user) return null;
    return (
      conversations.find((conversation) =>
        [conversation.participant_a_id, conversation.participant_b_id].includes(user.uid) &&
        [conversation.participant_a_id, conversation.participant_b_id].includes(contact.id)
      ) || null
    );
  };

  const startChat = async () => {
    if (!selectedNewContact) return alert("Choose a contact.");

    setBusy(true);
    try {
      const existing = findConversationForContact(selectedNewContact);
      const conversation = existing || (await createConversation(selectedNewContact));
      setSelectedConversationId(conversation.id);
      await loadChat();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Could not start chat.");
    } finally {
      setBusy(false);
    }
  };

  const sendReply = async () => {
    if (!user || !selectedConversation) return alert("Select a conversation.");
    const body = replyBody.trim();
    if (!body) return alert("Message is required.");

    setBusy(true);
    try {
      const { error } = await supabase.from("admin_chat_messages").insert({
        conversation_id: selectedConversation.id,
        sender_id: user.uid,
        sender_email: user.email,
        body,
      });

      if (error) throw error;
      setReplyBody("");
      await loadChat();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Message send failed.");
    } finally {
      setBusy(false);
    }
  };

  const publishAnnouncement = async () => {
    if (!user || !isAdmin) return;
    const publishToAll = isSuperAdmin && announcementAudience === "all";
    const orgId = publishToAll ? null : isSuperAdmin ? announcementOrgId.trim().toLowerCase() : user.orgId;
    const title = announcementTitle.trim();
    const body = announcementBody.trim();
    if (!publishToAll && !orgId) return alert("Org ID is required.");
    if (!title) return alert("Title is required.");
    if (!body) return alert("Announcement is required.");

    setBusy(true);
    try {
      const { error } = await supabase.from("org_announcements").insert({
        org_id: orgId,
        audience: publishToAll ? "all" : "org",
        author_id: user.uid,
        author_email: user.email,
        title,
        body,
        active: true,
      });

      if (error) throw error;
      setAnnouncementTitle("");
      setAnnouncementBody("");
      await loadAnnouncements();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Announcement publish failed.");
    } finally {
      setBusy(false);
    }
  };

  const archiveAnnouncement = async (announcement: OrgAnnouncementRow) => {
    const ok = window.confirm(`Archive this announcement?\n\n${announcement.title}`);
    if (!ok) return;

    setBusy(true);
    try {
      const { error } = await supabase
        .from("org_announcements")
        .update({
          active: false,
          updated_at: new Date().toISOString(),
        })
        .eq("id", announcement.id);

      if (error) throw error;
      await loadAnnouncements();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Announcement archive failed.");
    } finally {
      setBusy(false);
    }
  };

  const restoreAnnouncement = async (announcement: OrgAnnouncementRow) => {
    const ok = window.confirm(`Restore this announcement?\n\n${announcement.title}`);
    if (!ok) return;

    setBusy(true);
    try {
      const { error } = await supabase
        .from("org_announcements")
        .update({
          active: true,
          updated_at: new Date().toISOString(),
        })
        .eq("id", announcement.id);

      if (error) throw error;
      await loadAnnouncements();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Announcement restore failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl text-gray-900 mb-2">{isAdmin ? "Messages" : "Announcements"}</h1>
          <p className="text-gray-600">
            {isAdmin
              ? isSuperAdmin
                ? "Chat with organization admins and publish org announcements."
                : "Chat with the Super Admin, coordinate with same-org admins, and publish announcements."
              : `Announcements from your organization (${user?.orgId || "-"})`}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-gray-200">
        {isAdmin && (
          <button
            onClick={() => setActiveTab("messages")}
            className={`inline-flex items-center gap-2 px-4 py-3 border-b-2 text-sm transition-colors ${
              activeTab === "messages"
                ? "border-emerald-600 text-emerald-700"
                : "border-transparent text-gray-600 hover:text-gray-900"
            }`}
          >
            <Inbox className="w-4 h-4" />
            Admin Chat
          </button>
        )}
        <button
          onClick={() => setActiveTab("announcements")}
          className={`inline-flex items-center gap-2 px-4 py-3 border-b-2 text-sm transition-colors ${
            activeTab === "announcements"
              ? "border-emerald-600 text-emerald-700"
              : "border-transparent text-gray-600 hover:text-gray-900"
          }`}
        >
          <Megaphone className="w-4 h-4" />
          Announcements
        </button>
      </div>

      {activeTab === "messages" && isAdmin && (
        <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-6">
          <aside className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg text-gray-900">Conversations</h2>
              <div className="mt-4 flex gap-2">
                <select
                  value={newChatContactId}
                  onChange={(event) => setNewChatContactId(event.target.value)}
                  className="min-w-0 flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  {contacts.map((contact) => (
                    <option key={contact.id} value={contact.id}>
                      {contact.email} · {contact.super_admin ? "Super Admin" : contact.org_id}
                    </option>
                  ))}
                </select>
                <button
                  onClick={startChat}
                  disabled={busy || contacts.length === 0}
                  className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg disabled:opacity-60"
                  title="Start chat"
                >
                  <MessageSquare className="w-4 h-4" />
                </button>
              </div>
              {contacts.length === 0 && <p className="text-xs text-gray-500 mt-2">No chat contacts available.</p>}
            </div>

            <div className="divide-y divide-gray-200 max-h-[640px] overflow-y-auto">
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  onClick={() => setSelectedConversationId(conversation.id)}
                  className={`w-full text-left p-4 transition-colors ${
                    selectedConversationId === conversation.id
                      ? "bg-emerald-50"
                      : "bg-white hover:bg-gray-50"
                  }`}
                >
                  <div className="text-sm text-gray-900 truncate">{conversationContactLabel(conversation)}</div>
                  <div className="text-xs text-gray-500 mt-1">{formatDate(conversation.updated_at)}</div>
                </button>
              ))}
              {conversations.length === 0 && (
                <div className="p-4 text-sm text-gray-600">No conversations yet. Start one from the selector above.</div>
              )}
            </div>
          </aside>

          <section className="bg-white rounded-lg border border-gray-200 overflow-hidden min-h-[560px] flex flex-col">
            <div className="px-5 py-4 border-b border-gray-200">
              <h2 className="text-lg text-gray-900">
                {selectedConversation ? conversationContactLabel(selectedConversation) : "Select a conversation"}
              </h2>
              {selectedConversation && (
                <p className="text-xs text-gray-500 mt-1">Org: {selectedConversation.org_id}</p>
              )}
            </div>

            <div className="flex-1 p-5 space-y-4 overflow-y-auto bg-gray-50">
              {activeConversationMessages.map((message) => {
                const mine = message.sender_id === user?.uid;
                return (
                  <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[min(680px,85%)] rounded-lg px-4 py-3 ${
                        mine ? "bg-emerald-600 text-white" : "bg-white border border-gray-200 text-gray-800"
                      }`}
                    >
                      <div className={`text-xs mb-1 ${mine ? "text-emerald-50" : "text-gray-500"}`}>
                        {message.sender_email} · {formatTime(message.created_at)}
                      </div>
                      <p className="text-sm whitespace-pre-wrap">{message.body}</p>
                    </div>
                  </div>
                );
              })}
              {selectedConversation && activeConversationMessages.length === 0 && (
                <div className="text-sm text-gray-600">No messages in this conversation yet.</div>
              )}
              {!selectedConversation && (
                <div className="text-sm text-gray-600">Start or select a conversation to send replies.</div>
              )}
            </div>

            <div className="p-4 border-t border-gray-200 bg-white">
              <div className="flex flex-col sm:flex-row gap-3">
                <textarea
                  value={replyBody}
                  onChange={(event) => setReplyBody(event.target.value)}
                  rows={3}
                  disabled={!selectedConversation}
                  className="min-w-0 flex-1 px-3 py-2 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:bg-gray-50"
                  placeholder={selectedConversation ? "Write a reply..." : "Select a conversation first"}
                />
                <button
                  onClick={sendReply}
                  disabled={busy || !selectedConversation}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-60"
                >
                  <Send className="w-4 h-4" />
                  Send
                </button>
              </div>
            </div>
          </section>
        </div>
      )}

      {activeTab === "announcements" && (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-6">
          <section className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-lg text-gray-900">
                  {showArchivedAnnouncements ? "Archived Announcements" : "Organization Announcements"}
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  {showArchivedAnnouncements ? "Hidden announcements retained for admins." : "Active announcements by organization."}
                </p>
              </div>
              {isAdmin && (
                <button
                  onClick={() => {
                    setSelectedAnnouncementOrgId("");
                    setShowArchivedAnnouncements((value) => !value);
                  }}
                  className="inline-flex items-center justify-center gap-2 px-3 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm"
                >
                  {showArchivedAnnouncements ? (
                    <>
                      <Megaphone className="w-4 h-4" />
                      Active
                    </>
                  ) : (
                    <>
                      <Archive className="w-4 h-4" />
                      Archived
                    </>
                  )}
                </button>
              )}
            </div>
            <div className="divide-y divide-gray-200">
              {announcementGroups.map((group) => {
                const latest = group.announcements[0];
                return (
                  <button
                    key={group.orgId}
                    onClick={() => setSelectedAnnouncementOrgId(group.orgId)}
                    className="w-full text-left p-5 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-base text-gray-900">
                            {announcementGroupLabel(group.orgId)}{" "}
                            {showArchivedAnnouncements ? "Archived" : "Announcements"}
                          </h3>
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs ${
                              showArchivedAnnouncements ? "bg-gray-100 text-gray-700" : "bg-emerald-50 text-emerald-700"
                            }`}
                          >
                            {group.announcements.length}
                          </span>
                        </div>
                        <p className="text-sm text-gray-700 mt-2 truncate">{latest?.title || "No title"}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          Latest by {latest?.author_email || "-"}
                        </p>
                      </div>
                      <span className="text-xs text-gray-500 shrink-0">{formatDate(latest?.created_at || null)}</span>
                    </div>
                  </button>
                );
              })}
              {announcementGroups.length === 0 && (
                <div className="p-5 text-sm text-gray-600">
                  {showArchivedAnnouncements ? "No archived announcements available." : "No announcements available."}
                </div>
              )}
            </div>
          </section>

          {selectedAnnouncementGroup && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
              <section className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
                <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg text-gray-900">
                      {announcementGroupLabel(selectedAnnouncementGroup.orgId)}{" "}
                      {showArchivedAnnouncements ? "Archived Announcements" : "Announcements"}
                    </h2>
                    <p className="text-sm text-gray-500 mt-1">
                      {selectedAnnouncementGroup.announcements.length} announcement
                      {selectedAnnouncementGroup.announcements.length === 1 ? "" : "s"}
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedAnnouncementOrgId("")}
                    className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg"
                    title="Close"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <div className="overflow-y-auto divide-y divide-gray-200">
                  {selectedAnnouncementGroup.announcements.map((announcement) => (
                    <article key={announcement.id} className="p-5">
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className="text-sm text-gray-900">{announcement.title}</h3>
                          <p className="text-xs text-gray-500 mt-1">
                            {announcement.author_email} ·{" "}
                            {announcement.audience === "all"
                              ? "All Organizations"
                              : announcement.org_id}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs text-gray-500">{formatDate(announcement.created_at)}</span>
                          {isAdmin && (
                            showArchivedAnnouncements ? (
                              <button
                                onClick={() => restoreAnnouncement(announcement)}
                                disabled={busy}
                                className="inline-flex items-center gap-1 px-2 py-1 border border-emerald-200 text-emerald-700 rounded-md hover:bg-emerald-50 disabled:opacity-60 text-xs"
                                title="Restore announcement"
                              >
                                <RotateCcw className="w-3 h-3" />
                                Restore
                              </button>
                            ) : (
                              <button
                                onClick={() => archiveAnnouncement(announcement)}
                                disabled={busy}
                                className="inline-flex items-center gap-1 px-2 py-1 border border-gray-200 text-gray-700 rounded-md hover:bg-gray-50 disabled:opacity-60 text-xs"
                                title="Archive announcement"
                              >
                                <Archive className="w-3 h-3" />
                                Archive
                              </button>
                            )
                          )}
                        </div>
                      </div>
                      <p className="text-sm text-gray-700 mt-3 whitespace-pre-wrap">{announcement.body}</p>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          )}

          {isAdmin && (
            <section className="bg-white rounded-lg border border-gray-200 p-5 h-fit">
              <div className="flex items-center gap-2 mb-4">
                <Megaphone className="w-5 h-5 text-emerald-600" />
                <h2 className="text-lg text-gray-900">Publish Announcement</h2>
              </div>
              <div className="space-y-4">
                {isSuperAdmin ? (
                  <div>
                    <label className="block text-sm text-gray-700 mb-2">Audience</label>
                    <select
                      value={announcementAudience}
                      onChange={(event) => setAnnouncementAudience(event.target.value === "all" ? "all" : "org")}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    >
                      <option value="all">All Organizations</option>
                      <option value="org">Specific Organization</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Use All Organizations for system-wide announcements.
                    </p>
                    {announcementAudience === "org" && (
                      <input
                        value={announcementOrgId}
                        onChange={(event) => setAnnouncementOrgId(event.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 mt-3"
                        placeholder="techbin"
                      />
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
                    <UserRound className="w-4 h-4 text-gray-500" />
                    {user?.orgId}
                  </div>
                )}
                <div>
                  <label className="block text-sm text-gray-700 mb-2">Title</label>
                  <input
                    value={announcementTitle}
                    onChange={(event) => setAnnouncementTitle(event.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-2">Announcement</label>
                  <textarea
                    value={announcementBody}
                    onChange={(event) => setAnnouncementBody(event.target.value)}
                    rows={6}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <button
                  onClick={publishAnnouncement}
                  disabled={busy}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-60"
                >
                  <Megaphone className="w-4 h-4" />
                  Publish
                </button>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};
